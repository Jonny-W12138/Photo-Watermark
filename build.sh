#!/bin/bash

# 照片水印工具 macOS 应用构建脚本

echo "🚀 开始构建照片水印工具 macOS 应用程序"

# 检查是否在 macOS 上
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ 此脚本只能在 macOS 上运行"
    exit 1
fi

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python 3，请先安装 Python"
    exit 1
fi

# 安装依赖
echo "📦 安装依赖包..."
pip3 install -r requirements.txt
pip3 install pyinstaller

# 清理之前的构建
echo "🧹 清理之前的构建文件..."
rm -rf build dist *.spec

# 使用 PyInstaller 构建应用
echo "🔨 开始构建应用程序..."
pyinstaller \
    --name="照片水印工具" \
    --windowed \
    --onedir \
    --clean \
    --noconfirm \
    --add-data="template_manager.py:." \
    --add-data="watermark_engine.py:." \
    --hidden-import="PIL._tkinter_finder" \
    --hidden-import="PIL.Image" \
    --hidden-import="PIL.ImageDraw" \
    --hidden-import="PIL.ImageFont" \
    --hidden-import="PIL.ImageQt" \
    --hidden-import="PyQt6.QtCore" \
    --hidden-import="PyQt6.QtGui" \
    --hidden-import="PyQt6.QtWidgets" \
    app.py

if [ $? -eq 0 ]; then
    echo "✅ 应用程序构建成功！"
    echo "📍 应用程序位置: $(pwd)/dist/照片水印工具.app"
    
    # 询问是否创建 DMG
    read -p "是否创建 DMG 安装包？(y/N): " create_dmg
    if [[ $create_dmg =~ ^[Yy]$ ]]; then
        echo "📦 创建 DMG 安装包..."
        dmg_name="照片水印工具.dmg"
        
        # 删除旧的 DMG
        rm -f "$dmg_name"
        
        # 创建 DMG
        hdiutil create \
            -volname "照片水印工具" \
            -srcfolder "dist/照片水印工具.app" \
            -ov -format UDZO \
            "$dmg_name"
        
        if [ $? -eq 0 ]; then
            echo "✅ DMG 创建成功: $dmg_name"
        else
            echo "❌ DMG 创建失败"
        fi
    fi
    
    echo ""
    echo "🎉 构建完成！"
    echo "💡 使用说明："
    echo "   1. 双击 'dist/照片水印工具.app' 运行应用"
    echo "   2. 如果遇到安全提示，请在 系统偏好设置 > 安全性与隐私 中允许运行"
    echo "   3. 或者在终端中运行: xattr -cr 'dist/照片水印工具.app'"
    
else
    echo "❌ 构建失败"
    exit 1
fi
