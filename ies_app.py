import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import graphviz
import io
from ies_simulation import IESModel

# 设置页面配置
st.set_page_config(page_title="综合能源系统 (IES) 仿真平台", layout="wide")

st.title("⚡ 综合能源系统 (IES) 仿真建模平台")
st.markdown("""
通过左侧组件库选择设备，配置参数后点击 **开始仿真**。系统将自动构建拓扑并进行优化求解。
""")

# --- 侧边栏：组件库与参数配置 ---
st.sidebar.header("🛠 组件库 (Device Library)")

# 1. 设备选择
st.sidebar.subheader("选择要包含的设备")
selected_devices = []

# 基础设备 (默认可选)
if st.sidebar.checkbox("光伏 (PV)", value=True): selected_devices.append('pv')
if st.sidebar.checkbox("外部电网 (Grid)", value=True): selected_devices.append('grid')

st.sidebar.markdown("---")
# 转换设备
if st.sidebar.checkbox("电锅炉 (Electric Boiler)"): selected_devices.append('electric_boiler')

st.sidebar.markdown("**热泵家族 (制热/制冷互斥)**")
if st.sidebar.checkbox("空气源热泵 (ASHP)"): selected_devices.append('ashp')
if st.sidebar.checkbox("浅层地源热泵 (GSHP-Shallow)"): selected_devices.append('gshp_shallow')
if st.sidebar.checkbox("中深层地源热泵 (GSHP-Deep)"): selected_devices.append('gshp_deep')

st.sidebar.markdown("---")
if st.sidebar.checkbox("电解槽 (Electrolyzer)"): selected_devices.append('electrolyzer')
if st.sidebar.checkbox("燃料电池 (Fuel Cell - 产电产热)"): selected_devices.append('fuel_cell')

st.sidebar.markdown("---")
# 储能设备
if st.sidebar.checkbox("蓄电池 (Battery)"): selected_devices.append('battery')
if st.sidebar.checkbox("氢储能 (H2 Storage)"): selected_devices.append('h2_storage')

st.sidebar.markdown("---")
# 作者信息
st.sidebar.image("https://github.com/gwyxjtu.png", width=100)
st.sidebar.markdown("""
### 👨‍💻 作者信息 (Author)
**作者**: [gwyxjtu](https://github.com/gwyxjtu)  
**项目**: 综合能源系统 (IES) 仿真平台  
**技术栈**: PyPSA, Streamlit, Graphviz  
**开源协议**: MIT
""")

# 2. 参数配置
st.sidebar.header("⚙️ 参数设置")

with st.sidebar.expander("能源价格 (分时电价)"):
    price_mode = st.radio("电价模式", ["固定电价", "分时电价 (TOU)"])
    if price_mode == "固定电价":
        grid_price_val = st.slider("网购电价 (元/kWh)", 0.2, 1.5, 0.6)
        grid_price = [grid_price_val] * 24
    else:
        # 定义一个典型的分时电价
        tou_prices = []
        for h in range(24):
            if 0 <= h < 8:
                tou_prices.append(0.3) # 谷
            elif 10 <= h < 15 or 18 <= h < 21:
                tou_prices.append(1.0) # 峰
            else:
                tou_prices.append(0.6) # 平
        
        st.info("当前分时电价: 谷(0-8h): 0.3, 平: 0.6, 峰(10-15h, 18-21h): 1.0")
        grid_price = tou_prices

with st.sidebar.expander("设备详细参数 (装机容量 & 效率)"):
    st.markdown("### 🔌 电力设备")
    pv_cap = st.number_input("光伏 (PV) 装机容量 (kW)", value=1000)
    bat_cap = st.number_input("蓄电池最大放电功率 (kW)", value=100)
    bat_hours = st.number_input("蓄电池储存时长 (h)", value=4)
    
    st.markdown("### ♨️ 热力/转换设备")
    eb_cap = st.number_input("电锅炉装机容量 (kW)", value=2000)
    
    st.markdown("**空气源热泵 (ASHP)**")
    ashp_cap = st.number_input("ASHP 装机容量 (kW)", value=500)
    ashp_cop = st.number_input("ASHP 制热 COP", value=3.0)
    ashp_eer = st.number_input("ASHP 制冷 EER", value=3.5)
    
    st.markdown("**浅层地源热泵 (GSHP-S)**")
    gshp_s_cap = st.number_input("GSHP-S 装机容量 (kW)", value=1000)
    gshp_s_cop = st.number_input("GSHP-S 制热 COP", value=4.0)
    gshp_s_eer = st.number_input("GSHP-S 制冷 EER", value=4.5)
    
    st.markdown("**中深层地源热泵 (GSHP-D)**")
    gshp_d_cap = st.number_input("GSHP-D 装机容量 (kW)", value=500)
    gshp_d_cop = st.number_input("GSHP-D 制热 COP", value=5.0)
    gshp_d_eer = st.number_input("GSHP-D 制冷 EER", value=5.5)
    
    st.markdown("### 🧪 氢能设备")
    ely_cap = st.number_input("电解槽装机容量 (kW)", value=100)
    ely_eff = st.slider("电解槽效率", 0.5, 0.9, 0.75)
    
    fc_cap = st.number_input("燃料电池装机容量 (kW)", value=100)
    fc_eff_e = st.slider("燃料电池发电效率", 0.3, 0.8, 0.40)
    fc_eff_h = st.slider("燃料电池产热效率", 0.2, 0.6, 0.45)
    
    h2s_cap = st.number_input("氢储能最大放氢功率 (kW)", value=200)
    h2s_hours = st.number_input("氢储能储存时长 (h)", value=20)

# --- 数据准备 ---
hours = 24
np.random.seed(42)

input_data = {
    'hours': hours,
    # 负荷曲线
    'elec_load': [43.6, 43.6, 43.6, 43.6, 43.6, 43.6, 55.3, 56.1, 55.7, 54.8, 54.5, 54.5, 54.5, 54.5, 54.5, 54.5, 54.5, 54.5, 44.5, 43.6, 43.6, 43.6, 43.6, 43.6],
    'heat_load': [1600.2, 1632.0, 1669.3, 1714.7, 1771.1, 1818.9, 1858.1, 2626.1, 2724.2, 2605.0, 2419.0, 1991.3, 1904.3, 1560.7, 1996.4, 1455.8, 1429.8, 1666.8, 1755.0, 1626.3, 1715.2, 1655.7, 1496.5, 1520.4],
    'cool_load': [2, 2, 2, 2, 2, 5, 10, 15, 20, 25, 30, 35, 38, 40, 38, 35, 30, 25, 20, 15, 10, 5, 2, 2],
    'h2_load': [0.0] * 24,
    
    # PV 曲线 (归一化后再乘以容量)
    'pv_pu': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.5, 1.0, 0.6, 0.25, 0.05, 0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    
    # 设备参数 (从 UI 获取)
    'pv_p_nom': pv_cap,
    'grid_cost': grid_price,
    
    'boiler_p_nom': eb_cap,
    
    'ashp_p_nom': ashp_cap,
    'ashp_eff': ashp_cop,
    'ashp_eer': ashp_eer,
    
    'gshp_shallow_p_nom': gshp_s_cap,
    'gshp_shallow_eff': gshp_s_cop,
    'gshp_shallow_eer': gshp_s_eer,
    
    'gshp_deep_p_nom': gshp_d_cap,
    'gshp_deep_eff': gshp_d_cop,
    'gshp_deep_eer': gshp_d_eer,
    
    'ely_p_nom': ely_cap,
    'ely_eff': ely_eff,
    
    'fc_p_nom': fc_cap,
    'fc_eff_elec': fc_eff_e,
    'fc_eff_heat': fc_eff_h,
    
    'bat_p_nom': bat_cap,
    'bat_hours': bat_hours,
    
    'h2s_p_nom': h2s_cap,
    'h2s_hours': h2s_hours,
    
    'bat_eff_store': 0.9,
    'bat_eff_dispatch': 0.9,
}

# --- 主界面布局 ---
st.subheader("🏗 系统拓扑图 (Topology)")

import os
# 使用相对路径，避免绝对路径中的特殊字符（如 #）导致 Graphviz 解析失败
icon_dir = "icon"

dot = graphviz.Digraph(comment='IES Topology')
# 改为 TB (Top to Bottom) 布局，配合横向母线实现横向分布
dot.attr(rankdir='TB', size='12,6!', ratio='fill')
dot.attr(nodesep='0.5', ranksep='0.5')
# 设置全局字体为 Times-Roman (即 Times New Roman) 且颜色为黑色
dot.attr(fontname='Times-Roman', fontcolor='black')
dot.attr('node', fontname='Times-Roman', fontcolor='black')
dot.attr('edge', fontname='Times-Roman', fontcolor='black')

# 计算各母线连接的组件数量以确定宽度
elec_conn = 1  # 基础负载
if 'pv' in selected_devices: elec_conn += 1
if 'grid' in selected_devices: elec_conn += 1
if 'electric_boiler' in selected_devices: elec_conn += 1
if 'ashp' in selected_devices: elec_conn += 1
if 'gshp_shallow' in selected_devices: elec_conn += 1
if 'gshp_deep' in selected_devices: elec_conn += 1
if 'electrolyzer' in selected_devices: elec_conn += 1
if 'fuel_cell' in selected_devices: elec_conn += 1
if 'battery' in selected_devices: elec_conn += 1

heat_conn = 1
if 'electric_boiler' in selected_devices: heat_conn += 1
if 'ashp' in selected_devices: heat_conn += 1
if 'gshp_shallow' in selected_devices: heat_conn += 1
if 'gshp_deep' in selected_devices: heat_conn += 1
if 'fuel_cell' in selected_devices: heat_conn += 1

cool_conn = 1
if 'ashp' in selected_devices: cool_conn += 1
if 'gshp_shallow' in selected_devices: cool_conn += 1
if 'gshp_deep' in selected_devices: cool_conn += 1

h2_conn = 1
if 'electrolyzer' in selected_devices: h2_conn += 1
if 'fuel_cell' in selected_devices: h2_conn += 1
if 'h2_storage' in selected_devices: h2_conn += 1

# 动态宽度设置 (宽度 = 连接数 * 系数)
w_elec = str(max(2.5, elec_conn * 1.0))
w_heat = str(max(2.5, heat_conn * 1.0))
w_cool = str(max(2.5, cool_conn * 1.0))
w_h2 = str(max(2.5, h2_conn * 1.0))

# 定义母线节点 (横向线条形状 - Horizontal Busbar)
bus_style = {"shape": "box", "height": "0.04", "style": "filled", "fixedsize": "true", "penwidth": "0", "labelloc": "t", "fontsize": "12"}
dot.node('Bus_Elec', 'Elec Bus', width=w_elec, fillcolor='blue', fontcolor='black', **bus_style)
dot.node('Bus_Heat', 'Heat Bus', width=w_heat, fillcolor='red', fontcolor='black', **bus_style)
dot.node('Bus_Cool', 'Cool Bus', width=w_cool, fillcolor='cyan', fontcolor='black', **bus_style)
dot.node('Bus_H2', 'H2 Bus', width=w_h2, fillcolor='green', fontcolor='black', **bus_style)

# 定义负载节点
dot.node('Load_Elec', 'Elec Load', shape='none', image=os.path.join(icon_dir, "eleload.png"), labelloc='b')
dot.node('Load_Heat', 'Heat Load', shape='none', image=os.path.join(icon_dir, "heating.png"), labelloc='b')
dot.node('Load_Cool', 'Cool Load', shape='none', image=os.path.join(icon_dir, "cooling.png"), labelloc='b')
dot.node('Load_H2', 'H2 Load', shape='ellipse')

dot.edge('Bus_Elec', 'Load_Elec', color='blue')
dot.edge('Bus_Heat', 'Load_Heat', color='red')
dot.edge('Bus_Cool', 'Load_Cool', color='cyan')
dot.edge('Bus_H2', 'Load_H2', color='green')

# 根据选择添加组件和连线
if 'pv' in selected_devices:
    dot.node('PV', 'PV', shape='none', image=os.path.join(icon_dir, "pv.png"), labelloc='b')
    dot.edge('PV', 'Bus_Elec', color='blue')

if 'grid' in selected_devices:
    dot.node('Grid', 'Grid', shape='none', image=os.path.join(icon_dir, "grid.png"), labelloc='b')
    dot.edge('Grid', 'Bus_Elec', color='blue')
    
if 'electric_boiler' in selected_devices:
    dot.node('EB', 'EB', shape='none', image=os.path.join(icon_dir, "EB.png"), labelloc='b')
    dot.edge('Bus_Elec', 'EB', color='blue')
    dot.edge('EB', 'Bus_Heat', color='red')
    
hp_map = {'ashp': ('ASHP', 'ashp.png'), 'gshp_shallow': ('GSHP-S', 'heatpump2.png'), 'gshp_deep': ('GSHP-D', 'heatpump3.png')}
for hp_id, (hp_label, hp_icon) in hp_map.items():
    if hp_id in selected_devices:
        dot.node(hp_id, hp_label, shape='none', image=os.path.join(icon_dir, hp_icon), labelloc='b')
        dot.edge('Bus_Elec', hp_id, color='blue')
        dot.edge(hp_id, 'Bus_Heat', color='red')
        dot.edge(hp_id, 'Bus_Cool', color='cyan')
        
if 'electrolyzer' in selected_devices:
    dot.node('Ely', 'Ely', shape='none', image=os.path.join(icon_dir, "electrolyzer.png"), labelloc='b')
    dot.edge('Bus_Elec', 'Ely', color='blue')
    dot.edge('Ely', 'Bus_H2', color='green')
    
if 'fuel_cell' in selected_devices:
    dot.node('FC', 'FC', shape='none', image=os.path.join(icon_dir, "fuelcell.png"), labelloc='b')
    dot.edge('Bus_H2', 'FC', color='green')
    dot.edge('FC', 'Bus_Elec', color='blue')
    dot.edge('FC', 'Bus_Heat', color='red')
    
if 'battery' in selected_devices:
    dot.node('Bat', 'Battery', shape='none', image=os.path.join(icon_dir, "battery.png"), labelloc='b')
    dot.edge('Bus_Elec', 'Bat', dir='both', color='blue')
    
if 'h2_storage' in selected_devices:
    dot.node('H2S', 'H2 Storage', shape='none', image=os.path.join(icon_dir, "hydrogen storage.png"), labelloc='b')
    dot.edge('Bus_H2', 'H2S', dir='both', color='green')

try:
    png_data = dot.pipe(format='png')
    st.image(png_data, use_container_width=True)
except Exception:
    st.graphviz_chart(dot)

st.info("💡 提示：在左侧勾选设备，拓扑图将实时更新。")

st.markdown("---")
st.subheader("📊 数据预览 (负荷 & 电价)")
plt.rcParams['font.family'] = 'Times New Roman'
plt.rcParams['text.color'] = 'black'
fig_load, ax_load = plt.subplots(figsize=(12, 5))
ax_load.plot(input_data['elec_load'], label='Elec Load [kW]', color='blue', linewidth=2)
ax_load.plot(input_data['heat_load'], label='Heat Load [kW]', color='red', linestyle='--')
ax_load.plot(input_data['cool_load'], label='Cool Load [kW]', color='green', linestyle=':')
ax_load.set_ylabel("Power [kW]")
ax_load.set_xlabel("Hour")
ax_price = ax_load.twinx()
ax_price.step(range(24), input_data['grid_cost'], where='post', label='Grid Price [元/kWh]', color='orange', alpha=0.7)
ax_price.set_ylabel("Price [元/kWh]")
lines, labels = ax_load.get_legend_handles_labels()
lines2, labels2 = ax_price.get_legend_handles_labels()
ax_load.legend(lines + lines2, labels + labels2, loc='upper left')
plt.title("Input Load & Price Profiles")
st.pyplot(fig_load)

if st.button("🚀 开始仿真", type="primary"):
    with st.spinner("正在优化求解中..."):
        model = IESModel(input_data)
        model.build_model(components=selected_devices)
        
        if model.solve():
            st.success("仿真成功！")
            
            # --- 1. 全天工况统计输出 ---
            st.subheader("📋 全天工况统计 (Daily Operating Conditions)")
            
            try:
                # 提取各设备状态
                snapshots = model.n.snapshots
                df_status = pd.DataFrame(index=snapshots)
                
                # 处理发电机 (PV, Grid)
                for gen in model.n.generators.index:
                    if gen in model.n.generators_t.p.columns:
                        df_status[f"{gen}"] = model.n.generators_t.p[gen].apply(lambda x: "运行" if x > 0.1 else "停机")
                
                # 处理转换链路 (EB, HP, Ely, FC)
                # 分类汇总：制热、制冷、产氢、产电
                status_list = []
                for t in snapshots:
                    active_heat = []
                    active_cool = []
                    active_h2 = []
                    
                    # 检查制热设备
                    for link in ['electric_boiler', 'ashp_heating', 'gshp_shallow_heating', 'gshp_deep_heating', 'fuel_cell']:
                        if link in model.n.links_t.p0.columns and model.n.links_t.p0.at[t, link] > 0.1:
                            name = link.split('_')[0].upper()
                            active_heat.append(name)
                    
                    # 检查制冷设备
                    for link in ['ashp_cooling', 'gshp_shallow_cooling', 'gshp_deep_cooling']:
                        if link in model.n.links_t.p0.columns and model.n.links_t.p0.at[t, link] > 0.1:
                            name = link.split('_')[0].upper()
                            active_cool.append(name)
                            
                    # 检查产氢
                    if 'electrolyzer' in model.n.links_t.p0.columns and model.n.links_t.p0.at[t, 'electrolyzer'] > 0.1:
                        active_h2.append("ELY")
                        
                    status_list.append({
                        "时刻": f"{t:02d}:00",
                        "供热设备": ", ".join(active_heat) if active_heat else "无",
                        "供冷设备": ", ".join(active_cool) if active_cool else "无",
                        "产氢状态": "运行" if active_h2 else "停止"
                    })
                
                df_links = pd.DataFrame(status_list)
                
                # 处理储能状态 (Battery, H2 Storage)
                for storage in model.n.storage_units.index:
                    if storage in model.n.storage_units_t.p.columns:
                        def get_storage_mode(p):
                            if p > 0.1: return "放能"
                            elif p < -0.1: return "储能"
                            else: return "闲置"
                        df_links[f"{storage}状态"] = model.n.storage_units_t.p[storage].apply(get_storage_mode).values

                st.dataframe(df_links, use_container_width=True)
                
                # 统计摘要
                st.markdown("**🔍 工况特征摘要：**")
                summary_cols = st.columns(2)
                with summary_cols[0]:
                    if 'battery状态' in df_links.columns:
                        bat_charge = (df_links['battery状态'] == "储能").sum()
                        bat_discharge = (df_links['battery状态'] == "放能").sum()
                        st.write(f"- 🔋 蓄电池：全天储能 {bat_charge} 小时，放能 {bat_discharge} 小时")
                    if 'h2_storage状态' in df_links.columns:
                        h2_charge = (df_links['h2_storage状态'] == "储能").sum()
                        h2_discharge = (df_links['h2_storage状态'] == "放能").sum()
                        st.write(f"- ⛽ 氢储能：全天储氢 {h2_charge} 小时，放氢 {h2_discharge} 小时")
                
                with summary_cols[1]:
                    if '产氢状态' in df_links.columns:
                        h2_hours = (df_links['产氢状态'] == "运行").sum()
                        st.write(f"- 🧪 电解槽：全天运行 {h2_hours} 小时")
                    fc_hours = df_links['供热设备'].str.contains("FUEL").sum()
                    st.write(f"- ⚡ 燃料电池：全天运行 {fc_hours} 小时")

            except Exception as e:
                st.error(f"工况统计解析失败: {e}")

            # --- 2. 导出 Excel 结果 ---
            st.markdown("---")
            st.subheader("📥 下载运行结果 (Export Results)")
            
            try:
                # 获取所有结果
                all_res = model.get_all_results()
                
                # 创建内存中的 Excel 文件
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    for sheet_name, df in all_res.items():
                        if not df.empty:
                            df.to_excel(writer, sheet_name=sheet_name)
                
                excel_data = output.getvalue()
                
                st.download_button(
                    label="📂 点击下载全天运行数据 (Excel)",
                    data=excel_data,
                    file_name="ies_simulation_results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
                st.success("结果已汇总，点击上方按钮即可下载。")
                
            except Exception as e:
                st.error(f"Excel 导出失败: {e}")

            # 显示关键指标
            try:
                total_cost = model.n.objective
                st.metric("总运行成本", f"{total_cost:.2f} 元")
                
                cols = st.columns(3)
                for i, link in enumerate(model.n.links.index):
                    if not model.n.links_t.p0.empty and link in model.n.links_t.p0.columns:
                        max_p = model.n.links_t.p0[link].max()
                        cols[i % 3].write(f"**{link}** 最大功率: {max_p:.2f} kW")
            except Exception as e:
                st.error(f"无法计算指标: {e}")
        else:
            st.error("仿真失败，请检查模型约束或求解器设置。")

st.markdown("---")
st.caption("© 2026 综合能源系统 (IES) 仿真平台 | 由 [gwyxjtu](https://github.com/gwyxjtu) 开发 | Powered by PyPSA & Streamlit")
