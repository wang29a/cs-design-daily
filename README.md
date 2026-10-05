# 一日一设计

每日认真吃透一个计算机系统设计。当前完整收录 Unix 管道、虚拟内存、WAL、Git 对象与引用和 TCP 滑动窗口。

这个部署包只包含渲染后的阅读页和 GitHub Pages 工作流。站点可公开阅读，部署不需要付费模型 API，也不需要公开本机配置、对话历史或任务状态。

将本目录放入目标仓库的 main 分支，在仓库 Settings → Pages → Build and deployment 中选择 GitHub Actions。提交后，工作流部署 site/，成功后的访问地址由 Actions 的 deployment 输出提供，通常为 https://账户名.github.io/仓库名/。

每日新讲义继续由本机 Codex 定时任务生成。完成讲义、更新本地归档后，再运行本机 export_github.py 重新导出，把更新后的 site/index.html 提交到同一个仓库。工作流会自动部署新版本。生成新内容仍依赖本机任务执行成功；网页托管和读取不依赖本机开机。不要把重新部署已有内容当作生成了新讲义。

公开仓库内不保存访问令牌或本机路径配置。Pages 只上传 site/，README 和工作流不会作为网页文件发布。
