# Route Studio

本地运行的 iPhone / Android 路线编辑与模拟定位测试工具。浏览器中布设或导入 GPX 路线，连接已授权的测试手机后，可以设置起点、沿路线播放、暂停和清除模拟定位。Web 服务仅监听本机回环地址；“无线连接”指电脑与手机之间的连接，不会把控制接口开放到局域网。

## 启动与依赖

需要 Python 3.11+。安装项目依赖后，可运行 `ios-location-map` 或 `python -m ios_location_controller.web`，浏览器地址为 `http://127.0.0.1:8765`。Windows 的 `start-map.cmd` 与 Linux 的 `./start-map.sh` 可启动页面；Linux 可用 `./stop-server.sh` 停止。启动脚本依赖仓库根目录下已正确安装项目依赖的 `.venv`；虚拟环境不是项目源码的一部分，不应提交到 Git。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\start-map.cmd
```

Linux 环境可使用 `python3 -m venv .venv` 和 `./.venv/bin/python -m pip install -e ".[test]"` 准备依赖，再运行 `./start-map.sh`。Linux 连接 iPhone 还需要 `usbmuxd` 服务和 `libimobiledevice`；Windows 需要 Apple Mobile Device Support。

页面使用随包提供的 Leaflet JS/CSS。OpenStreetMap 底图和地点搜索需要网络；底图不可用时仍可输入坐标、编辑路线和控制设备。

## 路线与回放

“布设路线”页可在地图上添加、拖动、删除节点，也可输入坐标、导入 GPX、撤销和导出 GPX 1.1。节点按顺序直线连接，不会自动沿道路规划。编辑草稿保存在当前浏览器的 `localStorage`，编辑本身不会向手机发送位置。

“手机回放”页可载入草稿或导入 GPX。GPX 支持 `trkpt` 和 `rtept`，限制为 2 MB、最多 10000 个节点。连接手机且已有路线时会发送起点；只有点击“开始移动”才会沿路线播放。速度、配速、速度波动、横向波动、更新间隔、随机种子和循环开关可调；播放中参数锁定，暂停后可修改。轨迹是测试模拟，不代表真实人体运动。

- **清空路线（编辑页）**：只删除当前浏览器草稿，不影响已载入的回放路线或手机定位。
- **停止并清除模拟**：停止播放并请求手机恢复真实定位，但保留已载入路线及会话文件，稍后仍可重播。
- **清空已载入路线（回放页）**：一键停止播放、清除手机上的模拟定位、移除回放路线与进度，并更新会话文件；编辑草稿保持不变。若设备清理失败，路线不会被删除，可重试。
- **断开连接**：关闭设备连接并请求清除模拟定位；已载入路线仍保留。

回放页还可搜索 OpenStreetMap Nominatim 地点并切换到选中坐标，不会修改路线。播放时须先暂停或停止。橙色标记默认显示最近成功发送的模拟位置，并非手机读回的真实 GPS。路线及参数保存在 `~/.ios-location-controller/session.json`；服务重启后会恢复数据，但不会自动连接设备或开始播放。可用 `IOS_LOCATION_STATE` 指定其他状态文件。

## 连接 iPhone

需要已信任电脑、启用开发者模式，并具备可用的 Apple Mobile Device Support 和开发者服务。iOS 17.4+ 默认使用 `pymobiledevice3` 的进程内 RSD 隧道；旧系统与 iOS 17.0–17.3 的兼容性未经过本项目真机覆盖。

Web 界面支持两种连接方式：

1. **已发现设备**：选择 usbmux 列表中的 iPhone。设备可能通过 USB 或已配置的 Wi-Fi 连接被发现。
2. **无线地址**：输入已建立的可信隧道输出的 `RSD Address` 和 `RSD Port`。RSD 地址通常是 IPv6，**不是** iPhone 的普通 Wi-Fi IP。隧道必须持续运行；本工具不会自动执行首次配对或创建供其他进程使用的外部隧道。

外部 RSD 模式仅显示发送的模拟坐标。默认连接会尝试通过 USB 转发本机 `8100` 到 WebDriverAgent；仅当手机上已有可用且获准定位的 WDA 时，页面才可能显示读回的“手机实测”位置。WDA 不是模拟定位的前提。[pymobiledevice3 隧道说明](https://github.com/doronz88/pymobiledevice3/blob/master/docs/guides/ios17-tunnels.md)

## 连接 Android

需要 Android SDK Platform-Tools 的 `adb` 在 `PATH` 中，或通过 `ADB_PATH` 指向其可执行文件。手机须启用系统定位并授权 ADB 调试。程序使用 Android 系统的 `cmd location providers` 测试定位接口，不需要 root 或辅助 APK；建议 Android 12+，但仍取决于具体 ROM 是否实现该接口。连接时会检测支持情况，不支持则报错。[AOSP 接口](https://android.googlesource.com/platform/frameworks/base/+/main/services/core/java/com/android/server/location/LocationShellCommand.java)

- **USB 或已发现的无线设备**：在回放页选择 Android，再从设备列表连接。
- **Android 11+ 无线调试**：先通过界面输入配对地址与六位配对码，再填写无线调试的连接地址。配对端口和连接端口不同，且端口可能变化；配对码不会保存。程序不会启用不安全的旧式 `adb tcpip 5555`。

Android 适配器会临时允许 shell 模拟定位权限，向 `gps` 和 `network` 测试定位源发送坐标；停止时移除测试源，正常断开时恢复原权限。模拟位置仍标记为 mock，应用可能拒绝或另行使用融合定位。强制终止、断电或连接中断可能阻止清理；同一会话内可重试断开。命令行 `clear` 可以移除前一进程遗留的测试源，但无法推断前一进程原有的权限状态。ADB 命令有延迟，初次测试建议至少 1 秒的更新间隔。[Android ADB 文档](https://developer.android.com/tools/adb)

## 命令行

`ios-location list`、`validate`、`play`、`clear`、`map` 均保留。不要同时让命令行与 Web 界面控制同一台手机。

```text
ios-location list --platform android
ios-location pair 192.168.1.20:37111
ios-location play routes/sample.gpx --platform android --address 192.168.1.20:37123 --speed-kmh 5
ios-location clear --platform android --udid DEVICE_SERIAL
ios-location play routes/sample.gpx --rsd-host fd00::1 --rsd-port 54321 --speed-kmh 5
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tests/browser_connections.py
```

普通自动测试和浏览器连接表单测试不会改变真机定位。浏览器测试依赖 Playwright 与 Microsoft Edge。`tests/browser_device.py` 是单独的实机测试，会短暂模拟路线位置；`artifacts/` 是测试截图/录屏目录，不应纳入版本控制。Android 与无线 iPhone 的真机兼容性尚未全面验证。

Linux 可用 `./.venv/bin/python -m pytest -q` 运行单元测试。浏览器测试脚本使用 Microsoft Edge，主要面向 Windows。
