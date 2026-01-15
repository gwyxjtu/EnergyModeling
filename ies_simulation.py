import pypsa
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

class IESModel:
    def __init__(self, data):
        """
        初始化综合能源系统模型
        :param data: 包含负荷、PV曲线和设备参数的字典
        """
        self.data = data
        self.hours = data.get('hours', 24)
        self.n = pypsa.Network()
        self.n.set_snapshots(range(self.hours))
        
    def build_model(self, components=None):
        """
        构建模型拓扑
        :param components: 可选的组件列表，如果为 None，则根据 self.data 构建默认全量模型
        """
        # 1. 添加母线 (Buses) - 默认存在
        self.n.add("Bus", "electricity", carrier="AC")
        self.n.add("Bus", "heat", carrier="heat")
        self.n.add("Bus", "cooling", carrier="cooling")
        self.n.add("Bus", "hydrogen", carrier="H2")

        # 2. 添加默认发电机 (电网和PV通常是基础)
        if components is None or 'grid' in components:
            self.n.add("Generator", "grid", 
                      bus="electricity", 
                      p_nom_extendable=True, 
                      marginal_cost=self.data.get('grid_cost'))
        
        if components is None or 'pv' in components:
            self.n.add("Generator", "pv", 
                      bus="electricity", 
                      p_nom=self.data.get('pv_p_nom', 100),
                      p_max_pu=self.data['pv_pu'], 
                      marginal_cost=self.data.get('pv_cost', 0.01))

        # 3. 根据组件列表添加 Link 和 Storage
        # 如果 components 为 None，则添加所有支持的设备
        all_devices = components if components is not None else [
            'electric_boiler', 'ashp', 'gshp_shallow', 'gshp_deep', 'electrolyzer', 'fuel_cell', 'battery', 'h2_storage'
        ]

        # 负载添加 (默认添加，或者根据是否有对应母线的设备动态添加)
        self.n.add("Load", "elec_load", bus="electricity", p_set=self.data['elec_load'])
        self.n.add("Load", "heat_load", bus="heat", p_set=self.data['heat_load'])
        self.n.add("Load", "cool_load", bus="cooling", p_set=self.data['cool_load'])
        if 'h2_load' in self.data:
            self.n.add("Load", "h2_load", bus="hydrogen", p_set=self.data['h2_load'])

        if 'electric_boiler' in all_devices:
            self.n.add("Link", "electric_boiler", 
                      bus0="electricity", 
                      bus1="heat", 
                      p_nom=self.data.get('boiler_p_nom', 20),
                      efficiency=self.data.get('boiler_eff', 0.98))

        # 热泵类型处理
        hp_types = {
            'ashp': ('ashp', '空气源热泵'),
            'gshp_shallow': ('gshp_shallow', '浅层地源热泵'),
            'gshp_deep': ('gshp_deep', '中深层地源热泵')
        }

        for hp_key, (prefix, name) in hp_types.items():
            if hp_key in all_devices:
                self.n.add("Link", f"{prefix}_heating", 
                          bus0="electricity", 
                          bus1="heat", 
                          p_nom=self.data.get(f'{prefix}_p_nom', 40),
                          efficiency=self.data.get(f'{prefix}_eff', 3.0))
                self.n.add("Link", f"{prefix}_cooling", 
                          bus0="electricity", 
                          bus1="cooling", 
                          p_nom=self.data.get(f'{prefix}_p_nom', 40),
                          efficiency=self.data.get(f'{prefix}_eer', 3.5))

        if 'electrolyzer' in all_devices:
            self.n.add("Link", "electrolyzer", 
                      bus0="electricity", 
                      bus1="hydrogen", 
                      p_nom=self.data.get('ely_p_nom', 50),
                      efficiency=self.data.get('ely_eff', 0.75))

        if 'fuel_cell' in all_devices:
            self.n.add("Link", "fuel_cell", 
                      bus0="hydrogen", 
                      bus1="electricity", 
                      bus2="heat",
                      p_nom=self.data.get('fc_p_nom', 50),
                      efficiency=self.data.get('fc_eff_elec', 0.45),
                      efficiency2=self.data.get('fc_eff_heat', 0.40))

        if 'battery' in all_devices:
            self.n.add("StorageUnit", "battery",
                      bus="electricity",
                      p_nom=self.data.get('bat_p_nom', 30),
                      max_hours=self.data.get('bat_hours', 4),
                      efficiency_store=self.data.get('bat_eff_store', 0.9),
                      efficiency_dispatch=self.data.get('bat_eff_dispatch', 0.9),
                      cyclic_state_of_charge=True,
                      marginal_cost=0.01) # 降低储能成本以鼓励使用

        if 'h2_storage' in all_devices:
            self.n.add("StorageUnit", "h2_storage",
                      bus="hydrogen",
                      p_nom=self.data.get('h2s_p_nom', 100),
                      max_hours=self.data.get('h2s_hours', 20),
                      efficiency_store=0.98,
                      efficiency_dispatch=0.98,
                      cyclic_state_of_charge=True,
                      marginal_cost=0.005)

    def solve(self):
        """
        运行优化求解，并添加自定义约束
        """
        def extra_functionality(n, snapshots):
            # 获取 Link 的功率变量
            if "Link-p" in n.model.variables:
                p_links = n.model.variables["Link-p"]
            else:
                return

            # 为每种热泵添加互斥约束
            for prefix in ['ashp', 'gshp_shallow', 'gshp_deep']:
                heating_name = f"{prefix}_heating"
                cooling_name = f"{prefix}_cooling"
                
                if heating_name in n.links.index and cooling_name in n.links.index:
                    p0_heat = p_links.sel(name=heating_name)
                    p0_cool = p_links.sel(name=cooling_name)
                    p_nom = n.links.at[heating_name, "p_nom"]
                    
                    # 1. 容量共享约束
                    n.model.add_constraints(p0_heat + p0_cool <= p_nom, name=f"{prefix}_capacity_sharing")

                    # 2. 互斥约束
                    n.model.add_variables(coords=[snapshots], name=f"{prefix}_mode", binary=True)
                    z = n.model.variables[f"{prefix}_mode"]
                    n.model.add_constraints(p0_heat - z * p_nom <= 0, name=f"{prefix}_heating_exclusion")
                    n.model.add_constraints(p0_cool - (1 - z) * p_nom <= 0, name=f"{prefix}_cooling_exclusion")

        success = False
        # 指定支持 MILP 的求解器
        for solver in ['gurobi', 'copt', 'glpk']:
            try:
                print(f"Attempting optimization with solver: {solver}")
                # 使用 extra_functionality 传递自定义约束
                results = self.n.optimize(solver_name=solver, extra_functionality=extra_functionality)
                status = results[0] if isinstance(results, tuple) else results
                if status == 'ok':
                    print(f"Optimization successful with {solver}")
                    success = True
                    break
            except Exception as e:
                print(f"Solver {solver} failed: {e}")
                continue
        
        if not success:
            try:
                print("Trying default solver...")
                self.n.optimize(extra_functionality=extra_functionality)
                success = True
            except Exception as e:
                print(f"All optimization attempts failed: {e}")
        return success

    def plot_results(self, save_path='ies_results.png', show=True):
        fig = plt.figure(figsize=(15, 18))
        
        # 子图 1: 电力平衡
        # ... (保持之前的绘图代码)
        plt.subplot(5, 1, 1)
        if not self.n.generators_t.p.empty:
            self.n.generators_t.p.plot.area(ax=plt.gca(), alpha=0.7)
        if not self.n.storage_units_t.p.empty and 'battery' in self.n.storage_units_t.p.columns:
            self.n.storage_units_t.p['battery'].plot(ax=plt.gca(), color='orange', label='Battery Dispatch', linewidth=2)
        if not self.n.links_t.p1.empty and 'fuel_cell' in self.n.links_t.p1.columns:
            self.n.links_t.p1['fuel_cell'].plot(ax=plt.gca(), color='brown', label='Fuel Cell Output (Elec)', linewidth=2)
        
        total_elec_cons = self.n.loads_t.p_set['elec_load'].copy()
        if not self.n.links_t.p0.empty:
            # 包含 电解槽、电锅炉、各类热泵 的耗电
            hp_cols = []
            for prefix in ['ashp', 'gshp_shallow', 'gshp_deep']:
                hp_cols.extend([f"{prefix}_heating", f"{prefix}_cooling"])
            
            cols = [c for c in (['electrolyzer', 'electric_boiler'] + hp_cols) if c in self.n.links_t.p0.columns]
            total_elec_cons += self.n.links_t.p0[cols].sum(axis=1)
        
        plt.plot(total_elec_cons, 'r-', label='Total Elec Demand', linewidth=1)
        plt.title("Electricity Balance")
        plt.ylabel("Power [kW]")
        plt.legend(loc='upper right')

        # 子图 2: 热力平衡
        plt.subplot(5, 1, 2)
        if not self.n.links_t.p1.empty:
            # 电锅炉和各类热泵制热
            hp_heating_cols = [f"{prefix}_heating" for prefix in ['ashp', 'gshp_shallow', 'gshp_deep']]
            cols = [c for c in (['electric_boiler'] + hp_heating_cols) if c in self.n.links_t.p1.columns]
            if cols:
                self.n.links_t.p1[cols].plot.area(ax=plt.gca(), alpha=0.7)
        
        # 增加燃料电池产热
        if not self.n.links_t.p2.empty and 'fuel_cell' in self.n.links_t.p2.columns:
            self.n.links_t.p2['fuel_cell'].plot(ax=plt.gca(), color='magenta', label='Fuel Cell Output (Heat)', linewidth=2)

        plt.plot(self.n.loads_t.p_set['heat_load'], 'k--', label='Heat Load', linewidth=2)
        plt.title("Heat Balance")
        plt.ylabel("Power [kW]")
        plt.legend(loc='upper right')

        # 子图 3: 冷却平衡
        plt.subplot(5, 1, 3)
        hp_cooling_cols = [f"{prefix}_cooling" for prefix in ['ashp', 'gshp_shallow', 'gshp_deep']]
        cols = [c for c in hp_cooling_cols if c in self.n.links_t.p1.columns]
        if not self.n.links_t.p1.empty and cols:
            self.n.links_t.p1[cols].plot.area(ax=plt.gca(), alpha=0.7, label='HP Cooling Output')
        plt.plot(self.n.loads_t.p_set['cool_load'], 'k--', label='Cooling Load', linewidth=2)
        plt.title("Cooling Balance")
        plt.ylabel("Power [kW]")
        plt.legend(loc='upper right')

        # 子图 4: 氢能平衡
        plt.subplot(5, 1, 4)
        if not self.n.links_t.p1.empty and 'electrolyzer' in self.n.links_t.p1.columns:
            self.n.links_t.p1[['electrolyzer']].plot.area(ax=plt.gca(), alpha=0.7, color='lightgreen', label='Electrolyzer Output (H2)')
        if not self.n.storage_units_t.p.empty and 'h2_storage' in self.n.storage_units_t.p.columns:
            self.n.storage_units_t.p['h2_storage'].plot(ax=plt.gca(), color='blue', label='H2 Storage Dispatch', linewidth=2)
        
        h2_cons = pd.Series(0, index=self.n.snapshots)
        if 'h2_load' in self.n.loads_t.p_set:
            h2_cons += self.n.loads_t.p_set['h2_load']
        if not self.n.links_t.p0.empty and 'fuel_cell' in self.n.links_t.p0.columns:
            h2_cons += self.n.links_t.p0['fuel_cell']
        
        plt.plot(h2_cons, 'k--', label='H2 Demand (FC + Load)', linewidth=2)
        plt.title("Hydrogen Balance")
        plt.ylabel("Power [kW_h2]")
        plt.legend(loc='upper right')

        # 子图 5: 储能状态 (SOC)
        plt.subplot(5, 1, 5)
        if not self.n.storage_units_t.state_of_charge.empty:
            self.n.storage_units_t.state_of_charge.plot(ax=plt.gca(), linewidth=2)
        plt.title("Storage State of Charge (SOC)")
        plt.ylabel("Energy [kWh]")
        plt.legend(loc='upper right')

        plt.tight_layout()
        plt.savefig(save_path)
        print(f"Results saved to '{save_path}'")
        if show:
            plt.show()
        return fig

# --- 外部输入数据准备 ---
hours = 24
np.random.seed(42)

input_data = {
    'hours': hours,
    # 负荷曲线

    'elec_load': [
                    43.60284744,
                    43.60284744,
                    43.60284744,
                    43.60284744,
                    43.60284744,
                    43.60284744,
                    55.33008112,
                    56.1242895,
                    55.72398048,
                    54.76855654,
                    54.50142864,
                    54.48319007,
                    54.48319007,
                    54.48319007,
                    54.48319007,
                    54.48319007,
                    54.48319007,
                    54.49026064,
                    44.49527126,
                    43.60284744,
                    43.60284744,
                    43.60284744,
                    43.60284744,
                    43.60284744,
                ],
    'heat_load':[ 
                    1600.190187,
                    1632.032254,
                    1669.301754,
                    1714.670348,
                    1771.140296,
                    1818.853456,
                    1858.058655,
                    2626.114782,
                    2724.193045,
                    2604.960738,
                    2419.049093,
                    1991.320396,
                    1904.314025,
                    1560.730439,
                    1996.425944,
                    1455.788939,
                    1429.822657,
                    1666.799084,
                    1754.978159,
                    1626.30254,
                    1715.165616,
                    1655.723477,
                    1496.522837,
                    1520.432862,
                ],
    'cool_load': [2, 2, 2, 2, 2, 5, 10, 15, 20, 25, 30, 35, 38, 40, 38, 35, 30, 25, 20, 15, 10, 5, 2, 2],
    'h2_load': [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0], # 假设一个基础氢负荷
    
    # PV 曲线
    'pv_pu': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 80.0, 200.0,391.174493, 243.068018, 104.04405, 22.347518, 3.000195, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    
    # 设备参数
    'pv_p_nom': 1000,
    'grid_cost': [
                0.2012,
                0.2012,
                0.2012,
                0.2012,
                0.2012,
                0.2012,
                0.5253,
                0.5253,
                0.5253,
                0.5253, 
                0.5253, 
                0.2012,
                0.2012,
                0.2012,
                0.5253,
                0.5253,
                0.8494,
                0.8494,
                0.8494,
                0.8494,
                0.8494,
                0.8494,
                0.8494,
                0.5253
            ],
    'ely_eff': 0.75,
    'fc_eff_elec': 0.40, # 燃料电池发电效率
    'fc_eff_heat': 0.45, # 燃料电池产热效率
    'hp_p_nom': 40,      # 热泵容量
    'hp_eff': 3.5,       # 热泵制热 COP
    'hp_eer': 4.0,       # 热泵制冷 EER
    'bat_p_nom': 100,
    'h2s_p_nom': 200,
    'h2s_hours': 20,
}

# --- 执行模拟 ---
if __name__ == "__main__":
    print(f"PyPSA Version: {pypsa.__version__}")
    
    model = IESModel(input_data)
    model.build_model()
    if model.solve():
        model.plot_results()
        
        # 打印关键指标
        try:
            total_cost = model.n.objective
            print(f"\nTotal Operation Cost: {total_cost:.2f} CNY")
            print("\nDevice Capacities and Utilization:")
            for link in model.n.links.index:
                if not model.n.links_t.p0.empty and link in model.n.links_t.p0.columns:
                    max_p = model.n.links_t.p0[link].max()
                    print(f" - {link}: Max Input Power = {max_p:.2f} kW")
        except Exception as e:
            print(f"\nCould not calculate metrics: {e}")
