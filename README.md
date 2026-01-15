# ⚡ 综合能源系统 (IES) 仿真优化平台

这是一个基于 **PyPSA** 和 **Streamlit** 开发的交互式综合能源系统 (IES) 建模与仿真平台。它支持多能（电、热、冷、氢）耦合系统的快速构建、运行优化和结果可视化。

## 🌟 主要功能

- **交互式建模**：通过 Web 界面勾选设备库中的组件，动态构建系统拓扑。
- **多能流支撑**：
  - **电力系统**：光伏 (PV)、外部电网、蓄电池。
  - **热力系统**：电锅炉、燃料电池产热、多种热泵。
  - **冷却系统**：热泵制冷模式。
  - **氢能系统**：电解槽、燃料电池、氢储能。
- **智能热泵家族**：支持空气源热泵 (ASHP)、浅层地源热泵 (GSHP-S) 和中深层地源热泵 (GSHP-D)，并具备“冷热互斥”物理约束。
- **经济调度优化**：
  - 支持**分时电价 (TOU)**，自动执行削峰填谷策略。
  - 基于线性规划 (LP) 或混合整数线性规划 (MILP) 寻找全天运行成本最低方案。
- **可视化分析**：
  - **动态拓扑图**：使用图标和语义化连线实时展示系统结构。
  - **能量平衡图**：详尽展示各类能源的生产与消费平衡。
  - **工况统计**：自动生成设备逐时启停状态及储能冲放统计表。

## 🛠️ 本地运行指南

### 1. 安装系统依赖
本项目使用 Graphviz 绘制拓扑图，需在操作系统中安装 Graphviz 软件：
- **macOS**: `brew install graphviz`
- **Windows**: 下载安装包并配置 `PATH` 环境变量。
- **Linux**: `sudo apt-get install graphviz`

### 2. 安装 Python 依赖
建议使用虚拟环境：
```bash
pip install -r requirements.txt
```

### 3. 启动应用
```bash
streamlit run ies_app.py
```

## 🚀 Streamlit Cloud 部署说明

如果你准备部署到 Streamlit Cloud，请确保仓库中包含以下文件：
1. `ies_app.py`: 主程序入口。
2. `ies_simulation.py`: 模型类定义。
3. `requirements.txt`: Python 库依赖。
4. `packages.txt`: **必须包含**，内容为 `graphviz`，用于 Streamlit Cloud 安装系统级绘图工具。
5. `icon/`: 存放组件图标的文件夹。

## 📂 文件结构
```text
EnergyModeling/
├── ies_app.py          # Streamlit Web 界面逻辑
├── ies_simulation.py   # 基于 PyPSA 的模型封装类
├── requirements.txt    # Python 依赖
├── packages.txt        # 系统级依赖 (针对 Streamlit Cloud)
├── icon/               # 设备图标资源
└── README.md           # 项目说明文档
```

## 📄 开源协议
本项目采用 MIT 协议开源。
