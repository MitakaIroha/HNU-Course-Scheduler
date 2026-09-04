# 湖南大学课程排程

一个基于 PySide6 的桌面课程排程工具，用于浏览湖南大学课程清单、导入个人课表、检查时间冲突并规划新的个人课表。

## 功能

- 导入学校课程清单，支持 `.xlsx` 和 `.xls`
- 全局搜索、字段筛选以及考核方式、课程分类、开课学院快捷筛选
- 导入 `.xlsx`、`.xls` 或 `.json` 格式的个人课表
- 按星期、节次和有效周次进行冲突检查
- 手动加课、退掉预选课程、撤销与恢复撤销
- 实时计算当前总学分
- 导出可再次导入的 `.xlsx` 个人课表
- 自动保存并恢复当前排课状态

## 环境要求

- Python 3.11 或更高版本
- Windows 10/11（主要测试环境）

## 安装运行

```powershell
git clone https://github.com/MitakaIroha/HNU-Course-Scheduler.git
cd HNU-Course-Scheduler
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\main.py
```

Linux 或 macOS 可使用对应平台的虚拟环境 Python 运行，但目前尚未完成界面兼容性验证。

## 使用方法

1. 点击“导入 Excel”，选择学校导出的课程清单。
2. 点击“导入个人课表”，载入已有课表。
3. 使用搜索和筛选查找课程，通过“加入我的课表”完成排课。
4. 在课表格子上单击可按时间筛选，再次单击取消；右键可移除课程。
5. 点击“导出课表”生成可重新导入的个人课表文件。

## 项目结构

- `main.py`：程序入口
- `ui_main.py`：主窗口及交互逻辑
- `ui_schedule.py`：课表绘制与文本交互
- `logic.py`：课程读取、筛选、冲突检查和学分计算
- `data_services.py`：个人课表解析、状态保存和课表导出
- `parser_utils.py`：星期、节次、周次和教室解析
- `models.py`：领域数据模型
- `tests/`：单元测试

## 隐私说明

课程清单、个人课表、导出课表和自动恢复文件可能包含姓名、学号、课程及班级信息，已通过 `.gitignore` 排除。提交代码前仍建议运行 `git status`，确认没有误提交真实教务数据。

## 已知限制

- 学分由个人课表中的课程名称和教师信息匹配课程清单后计算；课程清单缺失或同名课程信息不足时可能无法准确匹配。
- 应用当前面向湖南大学课程清单及个人课表格式。

## License

本项目采用 [MIT License](LICENSE)。
