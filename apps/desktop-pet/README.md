# 硅基生命状态 · Windows 桌宠

解压后双击 **Install-Windows.cmd**。发布包内附原生 x64 可执行文件，安装器把应用装入当前用户目录并创建开始菜单入口 Silicon Life State Pet。从源码运行安装器时，使用 Windows 的 .NET Framework 4.8 编译 Pet.cs。支持离线安装，升级前请先从托盘退出桌宠。

启动本地状态服务，在仪表盘「桌宠设置」生成只读配对码。右击桌面晶体，选择「连接本地服务」，输入配对码及服务端口。凭据由当前 Windows 用户的 DPAPI 加密保存。只在本机读取，没有云端请求。

双击晶体查看原文、事件 ID 和修订 ID。拖动晶体或底部铭牌可移动位置。右键菜单可切换主体、分身、主题、大小、置顶、开机启动和通知。按 Esc 隐藏，双击托盘图标恢复。点击请求通知打开原始记录。主体范围显示各分身自己的报告与共享历史，晶体的外观由用户选择。

从托盘退出后运行 **Uninstall-Windows.cmd** 可移除该用户的桌宠。若卸载时服务离线，可在仪表盘「桌宠设置」撤销所有桌宠配对。授权及数据库由独立的本地服务管理。

Windows x64: extract and run **Install-Windows.cmd**, then pair from the dashboard’s desktop pet section. Double-click the crystal for original records. Use its context menu or tray to change scope, theme, notifications or visibility. Exit before running **Uninstall-Windows.cmd**.

匹夫 · 岑衡川 · 沈回音
