"""StarClerk 卸载程序。

单独打包成 Uninstall.exe 放在安装目录里，不依赖后端那一套 FastAPI/lancedb，
所以这里全部用标准库自己算路径、自己删数据，体积小、启动也快。
"""
