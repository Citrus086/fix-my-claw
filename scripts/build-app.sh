#!/bin/bash
# 构建独立的 macOS .app 包
# 包含 Python CLI 和 Swift GUI

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
GUI_DIR="$PROJECT_ROOT/gui"
DIST_DIR="$PROJECT_ROOT/dist"
APP_NAME="FixMyClawGUI.app"
CLI_NAME="fix-my-claw"

echo "==> FixMyClaw 独立应用构建脚本"
echo "项目根目录: $PROJECT_ROOT"
echo ""

# 清理旧的构建产物
cleanup() {
    echo "==> 清理旧构建产物..."
    rm -rf "$DIST_DIR"
    rm -rf "$PROJECT_ROOT/build"
    rm -f "$PROJECT_ROOT/$CLI_NAME.spec"
}

# 使用 PyInstaller 打包 Python CLI
build_cli() {
    echo "==> 使用 PyInstaller 打包 CLI..."

    cd "$PROJECT_ROOT"

    # 创建临时虚拟环境来确保干净的打包
    echo "    创建临时虚拟环境..."
    python3 -m venv build-env
    source build-env/bin/activate

    # 安装依赖
    echo "    安装依赖..."
    pip install --quiet pyinstaller
    pip install --quiet -e .

    # 使用 PyInstaller 打包
    echo "    打包 CLI 可执行文件..."
    pyinstaller --onefile \
        --name "$CLI_NAME" \
        --clean \
        --noconfirm \
        --add-data "src/fix_my_claw/prompts:fix_my_claw/prompts" \
        --hidden-import=fix_my_claw \
        --hidden-import=fix_my_claw.cli \
        --hidden-import=fix_my_claw.config \
        --hidden-import=fix_my_claw.core \
        --hidden-import=fix_my_claw.health \
        --hidden-import=fix_my_claw.monitor \
        --hidden-import=fix_my_claw.repair \
        --hidden-import=fix_my_claw.state \
        --hidden-import=fix_my_claw.notify \
        --hidden-import=fix_my_claw.shared \
        --hidden-import=fix_my_claw.anomaly_guard \
        --hidden-import=fix_my_claw.runtime \
        --collect-all fix_my_claw \
        scripts/cli_entry.py

    # 清理虚拟环境
    deactivate
    rm -rf build-env

    echo "    CLI 打包完成: $DIST_DIR/$CLI_NAME"
}

# 构建 Swift GUI
build_gui() {
    echo "==> 构建 Swift GUI..."

    cd "$GUI_DIR"

    # 使用 Swift Package Manager 构建
    swift build -c release

    # 创建 .app 目录结构
    mkdir -p "$DIST_DIR/$APP_NAME/Contents/MacOS"
    mkdir -p "$DIST_DIR/$APP_NAME/Contents/Resources"

    # 复制可执行文件
    cp ".build/release/fix-my-claw-gui" "$DIST_DIR/$APP_NAME/Contents/MacOS/"

    # 复制 Info.plist (如果存在)
    if [ -f "$GUI_DIR/FixMyClawGUI.app/Contents/Info.plist" ]; then
        cp "$GUI_DIR/FixMyClawGUI.app/Contents/Info.plist" "$DIST_DIR/$APP_NAME/Contents/"
    fi

    # 复制图标 (如果存在)
    if [ -f "$GUI_DIR/FixMyClawGUI.app/Contents/Resources/AppIcon.icns" ]; then
        cp "$GUI_DIR/FixMyClawGUI.app/Contents/Resources/AppIcon.icns" "$DIST_DIR/$APP_NAME/Contents/Resources/"
    fi

    echo "    GUI 构建完成"
}

# 将 CLI 嵌入 .app
embed_cli() {
    echo "==> 将 CLI 嵌入 .app 包..."

    # 确保 CLI 存在
    if [ ! -f "$DIST_DIR/$CLI_NAME" ]; then
        echo "错误: CLI 文件不存在: $DIST_DIR/$CLI_NAME"
        exit 1
    fi

    # 复制 CLI 到 .app 包内
    cp "$DIST_DIR/$CLI_NAME" "$DIST_DIR/$APP_NAME/Contents/MacOS/"
    chmod +x "$DIST_DIR/$APP_NAME/Contents/MacOS/$CLI_NAME"

    echo "    CLI 已嵌入到 $DIST_DIR/$APP_NAME/Contents/MacOS/$CLI_NAME"
}

# 创建 DMG (可选)
create_dmg() {
    echo "==> 创建 DMG 安装包..."

    local DMG_NAME="FixMyClaw-GUI.dmg"
    local DMG_PATH="$DIST_DIR/$DMG_NAME"
    local TEMP_DMG="$DIST_DIR/temp.dmg"
    local VOLUME_NAME="FixMyClaw"

    # 创建临时目录
    local TEMP_DIR="$DIST_DIR/dmg_temp"
    mkdir -p "$TEMP_DIR"

    # 复制 .app 到临时目录
    cp -R "$DIST_DIR/$APP_NAME" "$TEMP_DIR/"

    # 创建 Applications 快捷方式
    ln -s /Applications "$TEMP_DIR/Applications"

    # 创建 DMG
    hdiutil create -volname "$VOLUME_NAME" \
        -srcfolder "$TEMP_DIR" \
        -ov -format UDZO \
        "$DMG_PATH"

    # 清理临时目录
    rm -rf "$TEMP_DIR"

    echo "    DMG 创建完成: $DMG_PATH"
}

# 验证构建
verify() {
    echo "==> 验证构建..."

    local APP_PATH="$DIST_DIR/$APP_NAME"
    local CLI_PATH="$APP_PATH/Contents/MacOS/$CLI_NAME"
    local GUI_PATH="$APP_PATH/Contents/MacOS/fix-my-claw-gui"

    echo "    检查文件结构..."
    [ -d "$APP_PATH" ] && echo "    ✓ .app 目录存在"
    [ -f "$CLI_PATH" ] && echo "    ✓ CLI 已嵌入"
    [ -f "$GUI_PATH" ] && echo "    ✓ GUI 可执行文件存在"
    [ -x "$CLI_PATH" ] && echo "    ✓ CLI 可执行"
    [ -x "$GUI_PATH" ] && echo "    ✓ GUI 可执行"

    # 测试 CLI
    echo ""
    echo "    测试 CLI..."
    "$CLI_PATH" --help > /dev/null 2>&1 && echo "    ✓ CLI 运行正常" || echo "    ✗ CLI 运行失败"

    echo ""
    echo "==> 构建完成!"
    echo ""
    echo "输出文件:"
    echo "  - .app: $DIST_DIR/$APP_NAME"
    if [ -f "$DIST_DIR/FixMyClaw-GUI.dmg" ]; then
        echo "  - DMG:  $DIST_DIR/FixMyClaw-GUI.dmg"
    fi
    echo ""
    echo "使用方法:"
    echo "  1. 直接打开 $DIST_DIR/$APP_NAME"
    echo "  2. 或拖拽到 /Applications 目录"
}

# 主流程
main() {
    local skip_dmg=false

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-dmg)
                skip_dmg=true
                shift
                ;;
            --clean)
                cleanup
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    cleanup
    build_cli
    build_gui
    embed_cli

    if [ "$skip_dmg" = false ]; then
        create_dmg
    fi

    verify
}

main "$@"
