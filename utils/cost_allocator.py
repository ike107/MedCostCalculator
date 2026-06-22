# utils/cost_allocator.py
import pandas as pd
import streamlit as st
from config import CHUO_DEFAULTS

def merge_and_calculate_patient_revenue(dfs_dict):
    if 'F' not in dfs_dict or dfs_dict['F'] is None:
        st.warning("Fファイルがないため結合処理をスキップします")
        return None
    D = dfs_dict['D'].copy()
    E = dfs_dict['E'].copy()
    F = dfs_dict['F'].copy()
    
    with st.spinner("Dファイルから入院単位の正確な収益を計算中..."):
        points = pd.to_numeric(D["行為点数"], errors='coerce').fillna(0.0)
        times = pd.to_numeric(D["行為回数"], errors='coerce').fillna(0.0)
        coef = pd.to_numeric(D["医療機関関係数"], errors='coerce').fillna(1.0)
        
        base_rev = points * times
        yen_pt_div = D["円点区分"].astype(str).str.strip()
        rev_corrected = base_rev.where(yen_pt_div != "0", base_rev * 10)
        
        data_div = D["データ区分"].astype(str).str.strip()
        D["計算収益"] = rev_corrected.where(data_div != "93", rev_corrected * coef)
        
        patient_revenue = D.groupby(["データ識別番号", "入院年月日"])["計算収益"].sum().reset_index()
        patient_revenue.rename(columns={"計算収益": "入院総収益"}, inplace=True)
        patient_revenue["入院総収益"] = patient_revenue["入院総収益"].round().astype(int)

    with st.spinner("DEFファイルのベース結合を処理中..."):
        e_keys = ["データ識別番号", "退院年月日", "入院年月日", "データ区分", "順序番号"]
        e_target_cols = e_keys + ["実施年月日", "レセプト科区分", "診療科区分", "医師コード", "病棟コード", "病棟区分", "入外区分", "施設タイプ", "行為回数", "行為点数", "円点区分"]
        e_subset = E[[col for col in e_target_cols if col in E.columns]].drop_duplicates()
        
        fe_merged = pd.merge(F, e_subset, on=e_keys, how='left')
        
        d_subset = D[["データ識別番号", "実施年月日", "分類番号", "医療機関関係数"]].drop_duplicates(subset=["データ識別番号", "実施年月日"])
        def_merged = pd.merge(fe_merged, d_subset, on=["データ識別番号", "実施年月日"], how='left')

        def_merged["患者内連番"] = def_merged.groupby(["データ識別番号", "入院年月日"]).cumcount()
        
        def_merged = pd.merge(def_merged, patient_revenue, on=["データ識別番号", "入院年月日"], how="left")
        def_merged["入院総収益"] = def_merged["入院総収益"].fillna(0)
        
        def_merged["収益"] = def_merged["入院総収益"].where(def_merged["患者内連番"] == 0, 0)
        def_merged["収益"] = def_merged["収益"].astype(int)
        
        def_merged = def_merged.drop(columns=["入院総収益"])
        return def_merged

def calculate_direct_costs(def_df, dfs_dict):
    with st.spinner("消費量および直接原価を計算中..."):
        masters = []
        if '医薬品マスタ' in dfs_dict and dfs_dict['医薬品マスタ'] is not None:
            med_df = dfs_dict['医薬品マスタ'].copy()
            med_df["マスタ区分"] = "医薬品"
            masters.append(med_df)
        if '特定器材マスタ' in dfs_dict and dfs_dict['特定器材マスタ'] is not None:
            mat_df = dfs_dict['特定器材マスタ'].copy()
            mat_df["マスタ区分"] = "特定器材"
            masters.append(mat_df)
            
        if not masters:
            def_df["償還価格"] = 0.0
            def_df["消費量"] = 0.0
            def_df["明細直接原価"] = 0
            def_df["直接原価"] = 0
            def_df["マスタ区分"] = "未登録"
            return def_df

        combined_master = pd.concat(masters, ignore_index=True).drop_duplicates(subset=["レセ電コード"], keep='first')
        merged_df = pd.merge(def_df, combined_master, on="レセ電コード", how="left")
        
        merged_df["償還価格"] = merged_df["償還価格"].fillna(0.0)
        merged_df["マスタ区分"] = merged_df["マスタ区分"].fillna("マスタ外（その他）")
        
        f_use = pd.to_numeric(merged_df["ใช้量" if "ใช้量" in merged_df.columns else "使用量"], errors='coerce').fillna(0.0)
        e_times = pd.to_numeric(merged_df["行為回数"], errors='coerce').fillna(0.0)
        merged_df["消費量"] = f_use * e_times

        temp_cost = merged_df["消費量"] * merged_df["償還価格"] * 0.90
        merged_df["明細直接原価"] = temp_cost.round().astype(int)
        
        patient_cost = merged_df.groupby(["データ識別番号", "入院年月日"])["明細直接原価"].sum().reset_index()
        patient_cost.rename(columns={"明細直接原価": "入院総直接原価"}, inplace=True)
        
        merged_df = pd.merge(merged_df, patient_cost, on=["データ識別番号", "入院年月日"], how="left")
        merged_df["入院総直接原価"] = merged_df["入院総直接原価"].fillna(0)
        
        merged_df["直接原価"] = merged_df["入院総直接原価"].where(merged_df["患者内連番"] == 0, 0)
        merged_df["直接原価"] = merged_df["直接原価"].astype(int)
        
        merged_df = merged_df.drop(columns=["入院総直接原価"])
        return merged_df

def flag_patient_count_target(merged_df, dfs_dict):
    with st.spinner("配賦基準マスタ（部署コード999）に基づく延べ患者判定中..."):
        if '配賦基準マスタ' in dfs_dict and dfs_dict['配賦基準マスタ'] is not None:
            base_master = dfs_dict['配賦基準マスタ']
            total_pt_codes = set(base_master.loc[base_master["部署コード"] == "999", "レセ電コード"].dropna().unique())
            merged_df["延べ患者カウント対象フラグ"] = merged_df["レセ電コード"].isin(total_pt_codes)
        else:
            merged_df["延べ患者カウント対象フラグ"] = False
            
        return merged_df

def generate_department_template(df):
    rows = []
    if "診療科区分" in df.columns:
        valid_dept = df["診療科区分"].dropna().unique()
        for d in valid_dept:
            d_str = str(d).strip()
            if d_str and d_str != "nan":
                rows.append({"部門区分": "診療科", "部署コード": d_str, "部署名": ""})
                
    if "病棟コード" in df.columns:
        valid_wards = df["病棟コード"].dropna().unique()
        for w in valid_wards:
            w_str = str(w).strip()
            if w_str and w_str != "nan":
                rows.append({"部門区分": "病棟", "部署コード": f"B{w_str}", "部署名": ""})
                
    template_df = pd.DataFrame(rows).drop_duplicates(subset=["部門区分", "部署コード"])
    
    chuo_df = pd.DataFrame(CHUO_DEFAULTS)
    chuo_df.rename(columns={"デフォルト部署名": "部署名"}, inplace=True)
    template_df = pd.concat([template_df, chuo_df], ignore_index=True)
    
    other_row = pd.DataFrame([{"部門区分": "その他", "部署コード": "9999", "部署名": "共通管理費"}])
    template_df = pd.concat([template_df, other_row], ignore_index=True)
    
    template_df["収益"] = 0
    template_df["費用"] = 0
    return template_df

def allocate_indirect_costs(df, dfs_dict):
    if '部署別費用マスタ' not in dfs_dict or dfs_dict['部署別費用マスタ'] is None:
        df["配賦間接費"] = 0
        return df

    cost_master = dfs_dict['部署別費用マスタ'].copy()
    base_master = dfs_dict['配賦基準マスタ'].copy() if '配賦基準マスタ' in dfs_dict else None
    
    df["allocated_cost_internal"] = 0.0
    
    with st.spinner("間接費用の配賦（按分）計算を実行中..."):
        # ① 診療科部門 の配賦
        dept1_costs = cost_master[cost_master["部門区分"] == "診療科"]
        for _, row in dept1_costs.iterrows():
            code = row["部署コード"]
            cost = row["費用"]
            if cost == 0: continue
            mask = (df["延べ患者カウント対象フラグ"] == True) & (df["診療科区分"] == code)
            denominator = mask.sum()
            if denominator > 0:
                df.loc[mask, "allocated_cost_internal"] += (cost / denominator)
                
        # ② 病棟部門 の配賦
        dept2_costs = cost_master[cost_master["部門区分"] == "病棟"]
        for _, row in dept2_costs.iterrows():
            code = row["部署コード"]
            cost = row["費用"]
            if cost == 0: continue
            actual_ward_code = code[1:] if code.startswith('B') else code
            mask = (df["延べ患者カウント対象フラグ"] == True) & (df["病棟コード"] == actual_ward_code)
            denominator = mask.sum()
            if denominator > 0:
                df.loc[mask, "allocated_cost_internal"] += (cost / denominator)

       # ③ 中央診療部門 の配賦
        dept3_costs = cost_master[cost_master["部門区分"] == "中央診療"]
        if len(dept3_costs) > 0 and base_master is not None:
            points = pd.to_numeric(df["行為明細点数"], errors='coerce').fillna(0.0)
            meds = pd.to_numeric(df["行為明細薬剤料"], errors='coerce').fillna(0.0)
            mats = pd.to_numeric(df["行為明細材料料"], errors='coerce').fillna(0.0)
            df["temp_base_amount"] = points + meds + mats
            
            q_div = df["円・点区分"].astype(str).str.strip()
            is_tensu = (q_div == "0") | (df["円・点区分"] == 0)
            df.loc[is_tensu, "temp_base_amount"] = df.loc[is_tensu, "temp_base_amount"] * 10
            
            base_master_sub = base_master[base_master["部署コード"] != "999"].drop_duplicates(subset=["レセ電コード", "部署コード"])
            target_lece_dict = {code: grp["レセ電コード"].unique() for code, grp in base_master_sub.groupby("部署コード")}
            
            for _, row in dept3_costs.iterrows():
                code = row["部署コード"]
                cost = row["費用"]
                name = row["部署名"]
                if cost == 0: continue
                
                target_leces = target_lece_dict.get(code, [])
                if len(target_leces) == 0: continue
                
                mask = df["レセ電コード"].isin(target_leces)
                denominator = df.loc[mask, "temp_base_amount"].sum()
                
                if denominator > 0:
                    allocation_ratio = cost / denominator
                    df.loc[mask, "allocated_cost_internal"] += (df.loc[mask, "temp_base_amount"] * allocation_ratio)
                else:
                    st.sidebar.error(f"⚠️ {name} ({code}) の分母が0のため配賦できません。")
            
            df = df.drop(columns=["temp_base_amount"])

        # ④ その他部門 の配賦
        dept4_costs = cost_master[cost_master["部門区分"] == "その他"]
        total_other_cost = dept4_costs["費用"].sum()
        if total_other_cost > 0:
            mask = (df["延べ患者カウント対象フラグ"] == True)
            denominator = mask.sum()
            if denominator > 0:
                df.loc[mask, "allocated_cost_internal"] += (total_other_cost / denominator)

    df["配賦間接費"] = df["allocated_cost_internal"].round().astype(int)
    df = df.drop(columns=["allocated_cost_internal"])
    return df