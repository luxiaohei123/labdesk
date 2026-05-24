# LabDesk - 示波器工作台

LabDesk 是一个基于 Python 的桌面示波器工作台，用于波形采集、实时预览、导出和报表级图片生成。它内置模拟后端，可直接运行；同时提供实验性的 SCPI / pyvisa 后端，用于连接真实仪器。

![LabDesk](assets/logo.jpg)

## 功能

- 原生 Tkinter + Matplotlib 桌面界面。
- 内置模拟示波器后端，适合演示和无硬件开发。
- 实验性的 VISA / SCPI 后端，支持 `pyvisa`。
- 后台线程实时采集波形，提供双预览面板。
- 支持多通道 CSV 导出、SVG 导出、PNG/BMP 截图。
- 提供通道、触发、测量、导出和原始命令控制台。
- 使用 INI 文件保存配置。
- 附带 PyInstaller 打包配置，可生成 Windows 可执行文件。


## 快速开始

```bash
git clone https://github.com/<your-account>/labdesk.git
cd labdesk
pip install -r requirements.txt
python labdesk.py
```

Windows 上也可以直接双击 `bootstrap_labdesk.bat` 完成首次安装并启动；
环境准备好后，直接双击 `start_labdesk.bat` 即可。

## 模拟模式

1. 将 `Interface` 保持为 `Simulated`。
2. 点击 `Discover`。
3. 选择一个示例资源并点击 `Connect`。
4. 然后可以直接使用 `RUN`、`SINGLE`、导出和测量功能。

## 真实仪器

1. 安装 `requirements.txt` 中的依赖。
2. 按连接方式安装 VISA runtime。
3. 通过 USB、LAN、GPIB 等方式连接示波器。
4. 将 `Interface` 切换为 `VISA (pyvisa)`。
5. 点击 `Discover`，选择资源后点击 `Connect`。
6. 在 Console 中测试 `*IDN?`、`:TRIG:STAT?` 等命令。

## 测试

```bash
python -m unittest discover -s tests -v
python -m py_compile labdesk.py core/engine.py core/acquisition.py core/__init__.py
```

## 打包

```bash
pip install pyinstaller
pyinstaller LabDesk.spec
```

生成文件在 `dist/`。
如果要重复打包，可以直接运行 `build_release.bat`。

## 发布说明

- `labdesk.ini` 是运行时配置，不应提交到仓库。
- `venv/` 和 `.venv/` 是本地虚拟环境，不应提交到仓库。
- `dist/` 和 `build/` 是打包产物，不应提交到仓库。
- `bootstrap_labdesk.bat` 用于首次安装和启动。
- `start_labdesk.bat` 用于日常启动。

## 许可证

MIT。详见 [LICENSE](LICENSE)。
