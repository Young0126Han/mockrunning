# Route Studio / iOS Location Controller

本地运行的路线编辑与 iPhone 定位测试工具，包含两个独立流程。

## 启动

- **Windows**：入口为 `start-map.cmd`（或运行 `start-map.ps1`）
- **Linux**：入口为 `./start-map.sh`（停止服务使用 `./stop-server.sh`）

网页地址 `http://127.0.0.1:8765`。
启动脚本检查服务健康状态，不会重复启动占用同一端口的进程。
Python 环境：`.venv`，Python 3.11+，`pymobiledevice3 >=11.15.5,<12`。

## 01 布设路线

- 地图单击添加编号节点，拖动节点调整位置；点击节点弹窗或右侧列表可以删除节点。
- 支持撤销、清空、坐标添加、导入 GPX 编辑及查看整条路线。
- 导出标准 GPX 1.1 文件（WGS84 经纬度）。节点按顺序直线连接，不自动沿道路规划。
- 草稿保存在当前浏览器的 localStorage；刷新页面不会丢失。
- “将当前路线载入手机回放”是直接传入第二流程的快捷入口。
- 编辑草稿本身不会向手机发送任何位置。

## 02 手机回放

在同一页面连接手机并导入 GPX，无需复制命令到终端。
设备发现列表与定位服务连接状态分开显示。连接且有路线时发送起点，点击开始后才移动。
GPX 支持 trkpt 和 rtept，最多 10000 节点、2 MB。大轨迹抽样显示节点标记，导出/回放仍保留全部点。

回放页的“输入地点并切换定位”可以搜索地点，选择结果后直接把该坐标发送为新的模拟位置，不修改路线。搜索使用 OpenStreetMap Nominatim，需要网络；搜索结果为空时可改用更明确的英文地名或地址。路线播放中不能直接切换地点，应先暂停或停止。

可调参数：速度（km/h）、配速（min/km，与速度互换）、速度波动百分比、左右波动米数、
波动周期、更新间隔、随机种子与循环开关。
播放中锁定参数；暂停后可以改参数并继续。随机种子在下一次重新开始时生效。
波动为平滑的测试轨迹扰动，并非生理意义的真人运动模型。

- 开始：从起点移动；暂停后同一按钮为“继续移动”。
- 暂停：保留进度和最后模拟位置，不累计暂停时间。
- 停止并清除模拟：停止任务并请求恢复真实定位。
- 断开：关闭定位连接并请求清除模拟。
- 完成：停在终点，直到停止或断开。循环时终点返回起点，非闭合路线会跳转。

橙色圆点和经纬度是最近成功发送的模拟位置，不是从手机读回的 GPS。
能否在某个手机应用中即时显示取决于该应用的定位权限、刷新和缓存。
不要将本工具用于替代真实导航。

连接时程序也会自动尝试通过 USB 转发本机 `8100` 到手机的 WebDriverAgent，并读取 `/wda/device/location`。如果 WDA 已在手机运行且获得“始终允许”定位权限，网页会显示“手机实测”并自动居中；否则会显示 WDA 错误，同时模拟定位功能仍可使用。开发者模式本身不会启动 WDA。

回放路线和参数保存在 `~/.ios-location-controller/session.json`。
服务重启后恢复数据，但不会自动连接或自动开始，避免意外改变定位。
可通过 `IOS_LOCATION_STATE` 环境变量指定其他状态文件。

## 连接要求

需要支持数据传输的 USB 线、已配对且启用开发者模式的 iPhone。
- **Windows**：需要 Apple Mobile Device Support。
- **Linux**：需要运行系统守护进程 `usbmuxd`（如 `sudo systemctl start usbmuxd`）以及 `libimobiledevice`。
iOS 17.4+ 默认通过 `PreferredRsdTunnel` 建立进程内 RSD 隧道，无需管理员权限或独立隧道进程。
iOS 17.0–17.3 的隧道支持依赖平台；该版本未在此项目实机验证。
旧 iOS 自动选择 USB lockdown；同样未做实机兼容性覆盖。
连接失败会显示原始错误，不能把“USB 已发现”视为“定位已连接”。

Leaflet JS/CSS 随项目本地提供；只有 OpenStreetMap 底图需要联网。
底图网络出错时显示提示，节点编辑、坐标输入及设备控制仍可运行。
界面仅监听 localhost，不对局域网开放。

## 验证

Windows:
```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tests/browser_smoke.py
```

Linux:
```bash
./.venv/bin/python -m pytest -q
```

浏览器测试依赖 Playwright 与 Microsoft Edge；录屏依赖 Playwright FFmpeg。
`tests/browser_device.py` 是显式的实机测试，会短暂设置 sample.gpx 的位置，然后停止并清除模拟。
普通测试不会连接或改变 iPhone 定位。
截图和浏览器录屏保存在 `artifacts`；重构前代码在 `backups`。

CLI 的 list/validate/play/clear 仍保留，网页回放使用独立的运动状态机。
不要同时让 CLI 和网页控制同一台手机。
