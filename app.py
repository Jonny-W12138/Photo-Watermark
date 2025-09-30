import os
import sys
import math
from typing import List, Optional, Tuple

from PIL import Image, ImageQt

from PyQt6.QtCore import Qt, QSize, QPointF
from PyQt6.QtGui import QPixmap, QIcon, QAction, QColor, QFont, QTransform
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog,
    QHBoxLayout, QVBoxLayout, QGridLayout, QGroupBox, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsTextItem, QSlider, QSpinBox, QDoubleSpinBox,
    QColorDialog, QComboBox, QLineEdit, QCheckBox, QMessageBox, QDialog, QFormLayout,
    QTabWidget
)

from watermark_engine import export_image
import template_manager as tm


SUPPORTED_INPUTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
OUTPUT_FORMATS = ["JPEG", "PNG"]


def pil_to_qpixmap(img: Image.Image) -> QPixmap:
    return QPixmap.fromImage(ImageQt.ImageQt(img))


def load_image_any(path: str) -> Optional[Image.Image]:
    try:
        img = Image.open(path)
        # Ensure RGBA for preview
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        return img
    except Exception:
        return None


class DraggableWatermarkItem(QGraphicsPixmapItem):
    """
    Watermark item for image watermark (pixmap). For text watermark, we will use a separate QGraphicsTextItem subclass.
    """
    def __init__(self, pixmap: QPixmap):
        super().__init__(pixmap)
        self.setFlags(
            self.flags()
            | QGraphicsPixmapItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsPixmapItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setOpacity(1.0)


class DraggableTextItem(QGraphicsTextItem):
    """
    Draggable text watermark. We use QGraphicsTextItem for real-time preview, final export relies on PIL render.
    """
    def __init__(self, text: str):
        super().__init__(text)
        self.setFlags(
            self.flags()
            | QGraphicsTextItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setOpacity(1.0)


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出选项")
        self.format_combo = QComboBox()
        self.format_combo.addItems(OUTPUT_FORMATS)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(0, 100)
        self.quality_slider.setValue(85)
        self.quality_label = QLabel("JPEG质量: 85")

        self.width_edit = QLineEdit()
        self.height_edit = QLineEdit()
        self.percent_edit = QLineEdit()

        self.name_rule_combo = QComboBox()
        self.name_rule_combo.addItems(["保留原文件名", "添加前缀", "添加后缀"])
        self.prefix_edit = QLineEdit()
        self.suffix_edit = QLineEdit()

        self.out_dir_btn = QPushButton("选择输出文件夹")
        self.out_dir_label = QLabel("未选择")
        self.ok_btn = QPushButton("导出")
        self.cancel_btn = QPushButton("取消")

        form = QFormLayout()
        form.addRow("格式", self.format_combo)
        form.addRow(self.quality_label, self.quality_slider)
        form.addRow("按宽度(px)", self.width_edit)
        form.addRow("按高度(px)", self.height_edit)
        form.addRow("按比例(如1.0或0.5)", self.percent_edit)
        form.addRow("命名规则", self.name_rule_combo)
        form.addRow("前缀", self.prefix_edit)
        form.addRow("后缀", self.suffix_edit)
        form.addRow(self.out_dir_btn, self.out_dir_label)

        btns = QHBoxLayout()
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addLayout(btns)
        self.setLayout(layout)

        self.quality_slider.valueChanged.connect(self._on_quality_change)
        self.out_dir_btn.clicked.connect(self._choose_dir)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn.clicked.connect(self.accept)
        self.format_combo.currentTextChanged.connect(self._on_format_change)
        self._on_format_change(self.format_combo.currentText())

    def _on_format_change(self, fmt: str):
        is_jpeg = fmt.upper() == "JPEG"
        self.quality_slider.setEnabled(is_jpeg)
        self.quality_label.setEnabled(is_jpeg)

    def _on_quality_change(self, v: int):
        self.quality_label.setText(f"JPEG质量: {v}")

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if d:
            self.out_dir_label.setText(d)

    def get_opts(self):
        fmt = self.format_combo.currentText().upper()
        w = self.width_edit.text().strip()
        h = self.height_edit.text().strip()
        p = self.percent_edit.text().strip()
        resize = {}
        if w:
            try:
                resize["width"] = int(w)
            except Exception:
                pass
        if h:
            try:
                resize["height"] = int(h)
            except Exception:
                pass
        if p:
            try:
                resize["percent"] = float(p)
            except Exception:
                pass
        name_rule = self.name_rule_combo.currentText()
        prefix = self.prefix_edit.text().strip()
        suffix = self.suffix_edit.text().strip()

        quality = self.quality_slider.value() if fmt == "JPEG" else None
        out_dir = self.out_dir_label.text()
        return {
            "format": fmt,
            "quality": quality,
            "resize": resize,
            "name_rule": name_rule,
            "prefix": prefix,
            "suffix": suffix,
            "out_dir": out_dir if out_dir and out_dir != "未选择" else None,
        }


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("照片水印工具")
        self.resize(1200, 800)

        # State
        self.images: List[str] = []
        self.current_index: int = -1
        self.base_img: Optional[Image.Image] = None  # PIL image
        self.preview_scale_factor: float = 1.0  # scene pixels to original pixels
        self.watermark_type: str = "text"  # "text" or "image"
        self.text_settings = {
            "text": "示例水印",
            "font_path": None,
            "font_size": 36,
            "color_rgba": (255, 255, 255, 255),
            "stroke_width": 0,
            "stroke_rgba": None,
            "shadow_offset": (0, 0),
            "shadow_rgba": None,
        }
        self.image_settings = {
            "wm_image_path": None,
            "wm_scale": 0.3,
        }
        self.global_settings = {
            "type": "text",
            "opacity": 1.0,
            "rotation_deg": 0.0,
            "position_preset": "center",
            "manual_pos_px": None,  # set by drag in preview (scene coords, then converted)
            "margin": (10, 10),
        }

        # UI Components
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(96, 96))
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.currentRowChanged.connect(self.on_list_change)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.dragEnterEvent = self.dragEnterEvent
        self.list_widget.dropEvent = self.dropEvent

        # Import buttons
        import_bar = QHBoxLayout()
        btn_add_files = QPushButton("导入图片")
        btn_add_dir = QPushButton("导入文件夹")
        import_bar.addWidget(btn_add_files)
        import_bar.addWidget(btn_add_dir)
        btn_add_files.clicked.connect(self.add_files)
        btn_add_dir.clicked.connect(self.add_dir)

        # Preview area
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(self.view.renderHints())
        self.base_item: Optional[QGraphicsPixmapItem] = None
        self.wm_item: Optional[QGraphicsPixmapItem] = None  # for image type
        self.wm_text_item: Optional[DraggableTextItem] = None  # for text type

        # Controls - tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_text_tab(), "文本水印")
        tabs.addTab(self._build_image_tab(), "图片水印")
        tabs.addTab(self._build_layout_tab(), "布局与导出")
        tabs.currentChanged.connect(self._on_tab_changed)

        # Templates
        tpl_bar = QHBoxLayout()
        self.tpl_combo = QComboBox()
        self.tpl_combo.addItems(tm.list_templates())
        btn_tpl_load = QPushButton("加载模板")
        btn_tpl_save = QPushButton("保存为模板")
        btn_tpl_delete = QPushButton("删除模板")
        tpl_bar.addWidget(QLabel("模板："))
        tpl_bar.addWidget(self.tpl_combo)
        tpl_bar.addWidget(btn_tpl_load)
        tpl_bar.addWidget(btn_tpl_save)
        tpl_bar.addWidget(btn_tpl_delete)
        btn_tpl_load.clicked.connect(self.load_template_clicked)
        btn_tpl_save.clicked.connect(self.save_template_clicked)
        btn_tpl_delete.clicked.connect(self.delete_template_clicked)

        # Layout main
        left = QVBoxLayout()
        left.addLayout(import_bar)
        left.addWidget(QLabel("已导入图片"))
        left.addWidget(self.list_widget)
        left.addLayout(tpl_bar)

        right = QVBoxLayout()
        right.addWidget(QLabel("预览"))
        right.addWidget(self.view)
        right.addWidget(tabs, stretch=0)

        root = QHBoxLayout()
        root.addLayout(left, stretch=1)
        root.addLayout(right, stretch=2)
        self.setLayout(root)

        # Load last settings
        last = tm.load_last_settings()
        if last:
            self._apply_settings_dict(last)

    # Tabs builders
    def _build_text_tab(self) -> QWidget:
        w = QWidget()
        layout = QGridLayout()

        self.text_input = QLineEdit(self.text_settings["text"])
        self.font_combo = QFontComboBoxSafe()
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 200)
        self.font_size_spin.setValue(self.text_settings["font_size"])
        self.bold_check = QCheckBox("粗体")
        self.italic_check = QCheckBox("斜体")
        self.color_btn = QPushButton("字体颜色")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(self.global_settings["opacity"] * 100))
        self.stroke_width_spin = QSpinBox()
        self.stroke_width_spin.setRange(0, 20)
        self.stroke_color_btn = QPushButton("描边颜色")
        self.shadow_offset_x = QSpinBox()
        self.shadow_offset_y = QSpinBox()
        self.shadow_offset_x.setRange(-50, 50)
        self.shadow_offset_y.setRange(-50, 50)
        self.shadow_color_btn = QPushButton("阴影颜色")

        self.rotate_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotate_slider.setRange(0, 360)
        self.rotate_slider.setValue(int(self.global_settings["rotation_deg"]))
        self.btn_preset_center = QPushButton("居中")
        self.btn_preset_tl = QPushButton("左上")
        self.btn_preset_tr = QPushButton("右上")
        self.btn_preset_bl = QPushButton("左下")
        self.btn_preset_br = QPushButton("右下")

        # layout
        row = 0
        layout.addWidget(QLabel("文本"), row, 0)
        layout.addWidget(self.text_input, row, 1, 1, 3); row += 1
        layout.addWidget(QLabel("字体"), row, 0)
        layout.addWidget(self.font_combo, row, 1)
        layout.addWidget(QLabel("字号"), row, 2)
        layout.addWidget(self.font_size_spin, row, 3); row += 1
        layout.addWidget(self.bold_check, row, 0)
        layout.addWidget(self.italic_check, row, 1)
        layout.addWidget(self.color_btn, row, 2)
        layout.addWidget(QLabel("透明度(%)"), row, 3); row += 1
        layout.addWidget(self.opacity_slider, row, 0, 1, 4); row += 1
        layout.addWidget(QLabel("描边宽度"), row, 0)
        layout.addWidget(self.stroke_width_spin, row, 1)
        layout.addWidget(self.stroke_color_btn, row, 2)
        layout.addWidget(QLabel("阴影偏移(x,y)"), row, 3); row += 1
        layout.addWidget(self.shadow_offset_x, row, 0)
        layout.addWidget(self.shadow_offset_y, row, 1)
        layout.addWidget(self.shadow_color_btn, row, 2); row += 1
        layout.addWidget(QLabel("旋转(°)"), row, 0)
        layout.addWidget(self.rotate_slider, row, 1, 1, 3); row += 1

        pos_layout = QHBoxLayout()
        pos_layout.addWidget(self.btn_preset_tl)
        pos_layout.addWidget(self.btn_preset_tr)
        pos_layout.addWidget(self.btn_preset_bl)
        pos_layout.addWidget(self.btn_preset_br)
        pos_layout.addWidget(self.btn_preset_center)
        layout.addLayout(pos_layout, row, 0, 1, 4); row += 1

        w.setLayout(layout)

        # connect
        self.text_input.textChanged.connect(self.on_text_changed)
        self.font_combo.currentFontChanged.connect(self.on_font_changed)
        self.font_size_spin.valueChanged.connect(self.on_font_size_changed)
        self.bold_check.toggled.connect(self.on_font_style_changed)
        self.italic_check.toggled.connect(self.on_font_style_changed)
        self.color_btn.clicked.connect(self.choose_text_color)
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        self.stroke_width_spin.valueChanged.connect(self.on_stroke_width_changed)
        self.stroke_color_btn.clicked.connect(self.choose_stroke_color)
        self.shadow_color_btn.clicked.connect(self.choose_shadow_color)
        self.shadow_offset_x.valueChanged.connect(self.on_shadow_offset_changed)
        self.shadow_offset_y.valueChanged.connect(self.on_shadow_offset_changed)
        self.rotate_slider.valueChanged.connect(self.on_rotate_changed)
        self.btn_preset_tl.clicked.connect(lambda: self.set_preset("top_left"))
        self.btn_preset_tr.clicked.connect(lambda: self.set_preset("top_right"))
        self.btn_preset_bl.clicked.connect(lambda: self.set_preset("bottom_left"))
        self.btn_preset_br.clicked.connect(lambda: self.set_preset("bottom_right"))
        self.btn_preset_center.clicked.connect(lambda: self.set_preset("center"))

        return w

    def _build_image_tab(self) -> QWidget:
        w = QWidget()
        layout = QGridLayout()

        self.btn_choose_logo = QPushButton("选择水印图片(PNG支持透明)")
        self.img_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.img_opacity_slider.setRange(0, 100)
        self.img_opacity_slider.setValue(int(self.global_settings["opacity"] * 100))
        self.img_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.img_scale_slider.setRange(1, 200)  # 0.01..2.0
        self.img_scale_slider.setValue(int(self.image_settings["wm_scale"] * 100))
        self.img_rotate_slider = QSlider(Qt.Orientation.Horizontal)
        self.img_rotate_slider.setRange(0, 360)
        self.img_rotate_slider.setValue(int(self.global_settings["rotation_deg"]))

        btn_tl = QPushButton("左上")
        btn_tr = QPushButton("右上")
        btn_bl = QPushButton("左下")
        btn_br = QPushButton("右下")
        btn_center = QPushButton("居中")

        row = 0
        layout.addWidget(self.btn_choose_logo, row, 0, 1, 3); row += 1
        layout.addWidget(QLabel("透明度(%)"), row, 0)
        layout.addWidget(self.img_opacity_slider, row, 1, 1, 2); row += 1
        layout.addWidget(QLabel("缩放(%)"), row, 0)
        layout.addWidget(self.img_scale_slider, row, 1, 1, 2); row += 1
        layout.addWidget(QLabel("旋转(°)"), row, 0)
        layout.addWidget(self.img_rotate_slider, row, 1, 1, 2); row += 1

        pos_layout = QHBoxLayout()
        pos_layout.addWidget(btn_tl)
        pos_layout.addWidget(btn_tr)
        pos_layout.addWidget(btn_bl)
        pos_layout.addWidget(btn_br)
        pos_layout.addWidget(btn_center)
        layout.addLayout(pos_layout, row, 0, 1, 3); row += 1

        w.setLayout(layout)

        # connect
        self.btn_choose_logo.clicked.connect(self.choose_logo)
        self.img_opacity_slider.valueChanged.connect(self.on_opacity_changed)
        self.img_scale_slider.valueChanged.connect(self.on_img_scale_changed)
        self.img_rotate_slider.valueChanged.connect(self.on_rotate_changed)
        btn_tl.clicked.connect(lambda: self.set_preset("top_left"))
        btn_tr.clicked.connect(lambda: self.set_preset("top_right"))
        btn_bl.clicked.connect(lambda: self.set_preset("bottom_left"))
        btn_br.clicked.connect(lambda: self.set_preset("bottom_right"))
        btn_center.clicked.connect(lambda: self.set_preset("center"))

        return w

    def _build_layout_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout()
        self.btn_export = QPushButton("批量导出...")
        layout.addWidget(self.btn_export)
        tip = QLabel("提示：预览中可拖拽水印到任意位置；导出时默认禁止选择原图片所在目录以避免覆盖。")
        tip.setWordWrap(True)
        layout.addWidget(tip)
        w.setLayout(layout)
        self.btn_export.clicked.connect(self.batch_export)
        return w

    # Drag and drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls]
        self._add_paths(paths)

    # Import
    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        self._add_paths(files)

    def add_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if dir_path:
            collected = []
            for root, _, files in os.walk(dir_path):
                for fn in files:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in SUPPORTED_INPUTS:
                        collected.append(os.path.join(root, fn))
            self._add_paths(collected)

    def _add_paths(self, paths: List[str]):
        added = 0
        for p in paths:
            if not p or not os.path.exists(p):
                continue
            if os.path.isdir(p):
                # handled in add_dir; skip here
                continue
            ext = os.path.splitext(p)[1].lower()
            if ext not in SUPPORTED_INPUTS:
                continue
            self.images.append(p)
            img = load_image_any(p)
            if img:
                thumb = img.copy()
                thumb.thumbnail((96, 96))
                pix = pil_to_qpixmap(thumb)
                item = QListWidgetItem(QIcon(pix), os.path.basename(p))
                item.setToolTip(p)
                self.list_widget.addItem(item)
                added += 1
        if added and self.current_index < 0:
            self.list_widget.setCurrentRow(0)

    def on_list_change(self, idx: int):
        self.current_index = idx
        if idx < 0 or idx >= len(self.images):
            return
        path = self.images[idx]
        self.base_img = load_image_any(path)
        self._update_preview()

    # Preview update
    def _update_preview(self):
        self.scene.clear()
        self.base_item = None
        self.wm_item = None
        self.wm_text_item = None

        if not self.base_img:
            return

        # Fit base image into view
        view_size = self.view.viewport().size()
        vw = max(100, view_size.width())
        vh = max(100, view_size.height())
        scale_factor_w = vw / self.base_img.width
        scale_factor_h = vh / self.base_img.height
        scale_factor = min(scale_factor_w, scale_factor_h)
        scale_factor = min(scale_factor, 1.0)  # do not upscale for preview
        self.preview_scale_factor = scale_factor

        disp_size = (max(1, int(self.base_img.width * scale_factor)), max(1, int(self.base_img.height * scale_factor)))
        disp_img = self.base_img.resize(disp_size, Image.Resampling.LANCZOS)
        base_pix = pil_to_qpixmap(disp_img)
        self.base_item = QGraphicsPixmapItem(base_pix)
        self.scene.addItem(self.base_item)

        # Watermark item
        self.global_settings["type"] = self.watermark_type
        if self.watermark_type == "text":
            text = self.text_settings["text"]
            self.wm_text_item = DraggableTextItem(text)
            qfont = QFont(self.font_combo.currentFont())
            qfont.setPointSize(self.text_settings["font_size"])
            qfont.setBold(self.bold_check.isChecked())
            qfont.setItalic(self.italic_check.isChecked())
            self.wm_text_item.setFont(qfont)
            rgba = self.text_settings["color_rgba"]
            self.wm_text_item.setDefaultTextColor(QColor(rgba[0], rgba[1], rgba[2], rgba[3]))
            self.wm_text_item.setOpacity(self.global_settings["opacity"])
            self.scene.addItem(self.wm_text_item)
            # Position preset or manual
            self._place_wm_item(self.wm_text_item)
            # Rotation
            self._rotate_item(self.wm_text_item, self.global_settings["rotation_deg"])
        else:
            # image watermark
            wm_path = self.image_settings["wm_image_path"]
            if wm_path and os.path.exists(wm_path):
                wm_img = Image.open(wm_path).convert("RGBA")
                scale = self.image_settings["wm_scale"]
                disp_wm = wm_img.resize(
                    (max(1, int(wm_img.width * scale * self.preview_scale_factor)),
                     max(1, int(wm_img.height * scale * self.preview_scale_factor))),
                    Image.Resampling.LANCZOS
                )
                wm_pix = pil_to_qpixmap(disp_wm)
                self.wm_item = DraggableWatermarkItem(wm_pix)
                self.wm_item.setOpacity(self.global_settings["opacity"])
                self.scene.addItem(self.wm_item)
                self._place_wm_item(self.wm_item)
                self._rotate_item(self.wm_item, self.global_settings["rotation_deg"])

        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _place_wm_item(self, item):
        # If manual position exists, place there (converted)
        if self.global_settings.get("manual_pos_px") is not None:
            mp = self.global_settings["manual_pos_px"]
            item.setPos(mp[0], mp[1])
            return
        # Place by preset
        preset = self.global_settings.get("position_preset", "center")
        base_rect = self.base_item.boundingRect()
        iw = 200  # approximate item width
        ih = 50   # approximate item height
        if isinstance(item, QGraphicsPixmapItem):
            br = item.boundingRect()
            iw = br.width()
            ih = br.height()
        elif isinstance(item, QGraphicsTextItem):
            br = item.boundingRect()
            iw = br.width()
            ih = br.height()

        margin = 10
        x_candidates = {
            "left": base_rect.left() + margin,
            "center": base_rect.left() + (base_rect.width() - iw) / 2,
            "right": base_rect.right() - iw - margin,
        }
        y_candidates = {
            "top": base_rect.top() + margin,
            "center": base_rect.top() + (base_rect.height() - ih) / 2,
            "bottom": base_rect.bottom() - ih - margin,
        }
        mapping = {
            "top_left": (x_candidates["left"], y_candidates["top"]),
            "top_center": (x_candidates["center"], y_candidates["top"]),
            "top_right": (x_candidates["right"], y_candidates["top"]),
            "center_left": (x_candidates["left"], y_candidates["center"]),
            "center": (x_candidates["center"], y_candidates["center"]),
            "center_right": (x_candidates["right"], y_candidates["center"]),
            "bottom_left": (x_candidates["left"], y_candidates["bottom"]),
            "bottom_center": (x_candidates["center"], y_candidates["bottom"]),
            "bottom_right": (x_candidates["right"], y_candidates["bottom"]),
        }
        pos = mapping.get(preset, mapping["center"])
        item.setPos(pos[0], pos[1])

    def _rotate_item(self, item, deg):
        transform = QTransform()
        br = item.boundingRect()
        cx = br.width() / 2
        cy = br.height() / 2
        transform.translate(item.pos().x() + cx, item.pos().y() + cy)
        transform.rotate(deg)
        transform.translate(-(item.pos().x() + cx), -(item.pos().y() + cy))
        item.setTransform(transform)

    # Callbacks for text tab
    def on_text_changed(self, s: str):
        self.watermark_type = "text"
        self.text_settings["text"] = s
        if self.wm_text_item:
            self.wm_text_item.setPlainText(s)
        self._update_preview()

    def on_font_changed(self, qfont: QFont):
        self.watermark_type = "text"
        # Path mapping not trivial; export uses PIL fallback font unless specific path provided
        self._update_preview()

    def on_font_size_changed(self, v: int):
        self.watermark_type = "text"
        self.text_settings["font_size"] = v
        self._update_preview()

    def on_font_style_changed(self, _=None):
        self.watermark_type = "text"
        self._update_preview()

    def choose_text_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.text_settings["color_rgba"] = (c.red(), c.green(), c.blue(), 255)
            self._update_preview()

    def on_opacity_changed(self, v: int):
        op = v / 100.0
        self.global_settings["opacity"] = op
        self._update_preview()

    def on_stroke_width_changed(self, v: int):
        self.text_settings["stroke_width"] = v
        self._update_preview()

    def choose_stroke_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.text_settings["stroke_rgba"] = (c.red(), c.green(), c.blue(), 255)
            self._update_preview()

    def choose_shadow_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.text_settings["shadow_rgba"] = (c.red(), c.green(), c.blue(), 128)
            self._update_preview()

    def on_shadow_offset_changed(self, _=None):
        self.text_settings["shadow_offset"] = (self.shadow_offset_x.value(), self.shadow_offset_y.value())
        self._update_preview()

    def on_rotate_changed(self, v: int):
        self.global_settings["rotation_deg"] = float(v)
        self._update_preview()

    def set_preset(self, key: str):
        self.global_settings["position_preset"] = key
        self.global_settings["manual_pos_px"] = None  # reset manual when preset chosen
        self._update_preview()

    # Image tab callbacks
    def choose_logo(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if f:
            self.image_settings["wm_image_path"] = f
            self.watermark_type = "image"
            self.global_settings["type"] = "image"
            self._update_preview()

    def on_img_scale_changed(self, v: int):
        self.image_settings["wm_scale"] = v / 100.0
        self.watermark_type = "image"
        self._update_preview()

    def _on_tab_changed(self, idx: int):
        # Switch watermark type based on tab
        self.watermark_type = "text" if idx == 0 else "image" if idx == 1 else self.watermark_type
        self.global_settings["type"] = self.watermark_type
        self._update_preview()

    # Templates
    def save_template_clicked(self):
        name, ok = QFileDialog.getSaveFileName(self, "保存模板", "", "Template (*.json)")
        if ok and name:
            base = os.path.splitext(os.path.basename(name))[0]
            tm.save_template(base, self._collect_settings_dict())
            self.tpl_combo.clear()
            self.tpl_combo.addItems(tm.list_templates())
            QMessageBox.information(self, "提示", "模板已保存")

    def load_template_clicked(self):
        name = self.tpl_combo.currentText()
        data = tm.load_template(name)
        if data:
            self._apply_settings_dict(data)
            QMessageBox.information(self, "提示", "模板已加载")
            self._update_preview()

    def delete_template_clicked(self):
        name = self.tpl_combo.currentText()
        if name:
            ok = tm.delete_template(name)
            if ok:
                self.tpl_combo.clear()
                self.tpl_combo.addItems(tm.list_templates())
                QMessageBox.information(self, "提示", "模板已删除")

    def closeEvent(self, event):
        tm.save_last_settings(self._collect_settings_dict())
        super().closeEvent(event)

    def _collect_settings_dict(self):
        return {
            "images": self.images,
            "current_index": self.current_index,
            "watermark_type": self.watermark_type,
            "text_settings": self.text_settings,
            "image_settings": self.image_settings,
            "global_settings": self.global_settings,
        }

    def _apply_settings_dict(self, d):
        self.images = d.get("images", [])
        self.list_widget.clear()
        for p in self.images:
            img = load_image_any(p)
            if img:
                thumb = img.copy()
                thumb.thumbnail((96, 96))
                item = QListWidgetItem(QIcon(pil_to_qpixmap(thumb)), os.path.basename(p))
                item.setToolTip(p)
                self.list_widget.addItem(item)
        self.current_index = d.get("current_index", -1)
        if self.current_index >= 0 and self.current_index < len(self.images):
            self.list_widget.setCurrentRow(self.current_index)
        self.watermark_type = d.get("watermark_type", "text")
        self.text_settings = d.get("text_settings", self.text_settings)
        self.image_settings = d.get("image_settings", self.image_settings)
        self.global_settings = d.get("global_settings", self.global_settings)

    # Export
    def batch_export(self):
        if not self.images:
            QMessageBox.warning(self, "警告", "请先导入图片")
            return
        dlg = ExportDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        opts = dlg.get_opts()
        out_dir = opts.get("out_dir")
        if not out_dir:
            QMessageBox.warning(self, "警告", "必须选择输出文件夹")
            return
        # Prevent exporting to original folder by default
        for p in self.images:
            if os.path.dirname(p) == out_dir:
                QMessageBox.warning(self, "警告", "为避免覆盖原图，禁止导出到原图片所在目录。请重新选择。")
                return

        fmt = opts["format"]
        quality = opts["quality"]
        resize = opts["resize"]
        name_rule = opts["name_rule"]
        prefix = opts["prefix"]
        suffix = opts["suffix"]

        count = 0
        for p in self.images:
            base = load_image_any(p)
            if not base:
                continue
            settings = {
                "type": self.watermark_type,
                "opacity": self.global_settings["opacity"],
                "rotation_deg": self.global_settings["rotation_deg"],
                "position_preset": self.global_settings["position_preset"] if self.global_settings.get("manual_pos_px") is None else None,
                "manual_pos_px": self.global_settings.get("manual_pos_px"),
                "margin": self.global_settings.get("margin", (10, 10)),
                "text": self.text_settings.get("text"),
                "font_path": self.text_settings.get("font_path"),
                "font_size": self.text_settings.get("font_size"),
                "color_rgba": self.text_settings.get("color_rgba"),
                "stroke_width": self.text_settings.get("stroke_width"),
                "stroke_rgba": self.text_settings.get("stroke_rgba"),
                "shadow_offset": self.text_settings.get("shadow_offset"),
                "shadow_rgba": self.text_settings.get("shadow_rgba"),
                "wm_image_path": self.image_settings.get("wm_image_path"),
                "wm_scale": self.image_settings.get("wm_scale"),
            }
            composed = export_image(base, settings, {"format": fmt, "quality": quality, "resize": resize}, preview_scale_factor=self.preview_scale_factor)
            # Naming
            base_name = os.path.splitext(os.path.basename(p))[0]
            if name_rule == "添加前缀" and prefix:
                out_name = prefix + base_name
            elif name_rule == "添加后缀" and suffix:
                out_name = base_name + suffix
            else:
                out_name = base_name
            ext = ".jpg" if fmt == "JPEG" else ".png"
            out_path = os.path.join(out_dir, out_name + ext)

            save_kwargs = {}
            if fmt == "JPEG":
                save_kwargs["quality"] = int(quality) if quality is not None else 85
                save_kwargs["format"] = "JPEG"
                # JPEG doesn't support alpha; convert
                composed = composed.convert("RGB")
            else:
                save_kwargs["format"] = "PNG"

            try:
                composed.save(out_path, **save_kwargs)
                count += 1
            except Exception as e:
                print("保存失败:", e)

        QMessageBox.information(self, "完成", f"已导出 {count} 张图片到：{out_dir}")

    # Track manual drag position
    def mouseReleaseEvent(self, event):
        # After dragging, record manual position in scene coords
        if self.wm_item and self.scene.items():
            pos = self.wm_item.pos()
            self.global_settings["manual_pos_px"] = (pos.x(), pos.y())
        elif self.wm_text_item and self.scene.items():
            pos = self.wm_text_item.pos()
            self.global_settings["manual_pos_px"] = (pos.x(), pos.y())
        super().mouseReleaseEvent(event)


class QFontComboBoxSafe(QComboBox):
    """
    Lightweight font selector fallback if QFontComboBox is not imported.
    Uses QFontDatabase via QFontComboBox if available; else provides common choices.
    """
    def __init__(self):
        super().__init__()
        try:
            from PyQt6.QtWidgets import QFontComboBox
            self.inner = QFontComboBox()
            self.setModel(self.inner.model())
            self.currentFontChanged = self.inner.currentFontChanged
        except Exception:
            # Fallback common fonts
            self.addItems(["Arial", "Helvetica", "Times New Roman", "Courier New"])
            self.currentFontChanged = self._dummy_signal

    def currentFont(self) -> QFont:
        try:
            return self.inner.currentFont()
        except Exception:
            return QFont(self.currentText())

    def _dummy_signal(self, *args, **kwargs):
        pass


def main():
    app = QApplication(sys.argv)
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()