# Visual Vibe Coding

一个用 **模板化 Mermaid 流程框图** 来描述和生成代码结构的概念验证原型。

English version: [README_EN.md](README_EN.md)

我的核心想法很简单：**在 vibe coding 这种大模型参与度很高的开发方式里，纯文本提示词常常太松散、太难维护**。而流程框图天然更结构化，尤其是 Mermaid 这种轻量、可读、可编辑的图形语言，大语言模型对它的理解通常也很强。

我希望把“提示词”从一段松散的自然语言，变成一张可以被分块、分层、逐步修改的结构图，让代码块之间的输入、输出、成员状态和职责边界都更清晰。

## English Summary

Visual Vibe Coding is a proof-of-concept editor for describing software structure with template-based Mermaid flowcharts.

It explores a simple idea: instead of writing long, fragile prompt text for vibe coding, use structured diagrams to define modules, functions, I/O boundaries, and responsibilities. The goal is to make prompts easier to iterate, easier to collaborate on, and easier for large language models to understand.

## 为什么用框图做提示词

1. 让提示词结构化、模块化，便于局部修改，也更适合多人协作优化。
2. 可以分块、分层描述代码功能，通过严格定义 I/O 和程序行为，让 AI 按职责拆分实现，降低耦合和维护失控的风险。
3. 降低提示词撰写门槛，让非专业人士也能把想法快速转成结构清晰的程序流程。

## 这是一个什么项目

这是一个 **PoC（概念验证）原型**，不是成熟产品。

请注意：

- 里面包含大量未经人工审查的 vibe coding 代码。
- 图形化界面也比较粗糙，主要目标是验证思路。
- 当前重点是“流程图作为提示词载体”这件事，而不是做一个完整、漂亮、生产级的编辑器。

## 功能概览

- 用不同模板表示不同语义角色，例如 `program`、`module`、`class`、`function`、`interface` 等。
- 通过图形化方式编辑节点、嵌套节点、调整大小。
- 显式编辑输入、输出和成员变量，让结构更接近真实程序。
- 通过端口建立连接，强调输出到输入的约束关系。
- 支持导入和导出 Mermaid `.mmd` 文件。
- 在 Mermaid 文本中嵌入元数据，尽量保留节点位置、尺寸、父子关系和连线信息。

## 示例文件

仓库里包含两个示例：

- [calculator.mmd](calculator.mmd)  
  一个四则计算器的 Mermaid 示例，展示了如何用图框来表达流程、I/O 和成员状态。
- [test_vibe_coding.py](test_vibe_coding.py)  
  对应的示例 Python 脚本，用来演示从流程图表达出来的结构如何落成代码。(thanks to Grok！)

- [program_flow.mmd](program_flow.mmd)  
  这个项目程序本身的运行流程图，描述启动、编辑、导入导出和端口交互。

## 项目结构

- [main.py](main.py) 入口文件。
- [app/templates.py](app/templates.py) 模板定义。
- [app/graphics_items.py](app/graphics_items.py) 节点和连线的图形对象。
- [app/editor_window.py](app/editor_window.py) 主编辑器窗口和交互逻辑。

## 安装与运行

### 1. 创建并激活虚拟环境

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 启动程序

```powershell
python main.py
```

## 使用方式

1. 新建或载入一个 Mermaid 流程图。
2. 用不同模板组织程序块，明确每个块的职责。
3. 在节点里补充输入、输出和成员变量，尽量把行为边界写清楚。
4. 用连线表达数据流和调用关系。
5. 导出 `.mmd` 文件，作为后续 vibe coding 的结构化提示词。
6. 随便找个能读.mmd的agent喂给它

## 设计思路

这个原型想解决的是：**复杂项目里，纯文本很难清晰描述程序结构**。

当项目开始变复杂时，自然语言提示词容易出现这些问题：

- 结构散。
- 局部修改困难。
- 多人协作时风格不统一。
- AI 生成的代码容易耦合过强，边界不清楚。

而流程框图把这些信息显式化后，能更容易做到：

- 模块拆分。
- I/O 约束。
- 层级关系。
- 局部迭代。

## 当前局限

- 仍然只是原型，交互和视觉都比较朴素。
- 适合做思路验证，不适合直接当成完整的生产级编辑器。
- Mermaid 导入导出能力仍然依赖当前实现的元数据格式。

## 许可证

This project is licensed under the [MIT License](LICENSE).
