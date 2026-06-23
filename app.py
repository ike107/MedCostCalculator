# app.py
import pandas as pd
import streamlit as st

from config import D_COLUMNS, E_COLUMNS, F_COLUMNS
from utils.data_loader import (
    load_dpc_file, load_master_file, load_allocation_base_master, load_department_cost_master
)
from utils.cost_allocator import (
    merge_and_calculate_patient_revenue, calculate_direct_costs,
    flag_patient_count_target, generate_department_template, allocate_indirect_costs
)

@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf_8_sig')

def main():
    st.title("DPCデータ 損益計算（PL）ダッシュボード")
    
    # ─── ① まずはじめにDPCデータ、配賦基準マスタ、医薬品マスタ、特定器材マスタを取り込みます ───
    st.header("1. データのアップロード（ファーストステップ）")
    tab1, tab2 = st.tabs(["📊 DPCデータファイル (D・E・F)", "📋 必須マスタ"])
    
    with tab1:
        st.subheader("DPCデータ（厚生労働省標準様式）")
        d_file = st.file_uploader("Dファイルをアップロードしてください（必須）", type=["txt", "tsv"])
        e_file = st.file_uploader("Eファイルをアップロードしてください（必須）", type=["txt", "tsv"])
        f_file = st.file_uploader("Fファイルをアップロードしてください（必須）", type=["txt", "tsv"])
        
    with tab2:
        st.subheader("配賦基準および出来高単価マスタ")
        allocation_base_file = st.file_uploader("配賦基準マスタをアップロードしてください (.tab)", type=["tab", "txt"])
        med_file = st.file_uploader("医薬品マスタをアップロードしてください (.csv)", type=["csv"])
        mat_file = st.file_uploader("特定器材マスタをアップロードしてください (.csv)", type=["csv"])

    dfs = {}

    if d_file:
        d_num = ["行為点数", "行為薬剤料", "行為材料料", "行為回数", "医療機関関係数"]
        dfs['D'] = load_dpc_file(d_file, D_COLUMNS, numeric_cols=d_num)
        if dfs['D'] is not None: st.sidebar.success("✅ Dファイル 読込成功")

    if e_file:
        e_num = ["行為点数", "行為薬剤料", "行為材料料", "行為回数"]
        dfs['E'] = load_dpc_file(e_file, E_COLUMNS, numeric_cols=e_num)
        if dfs['E'] is not None: st.sidebar.success("✅ Eファイル 読込成功")

    if f_file:
        f_num = ["使用量", "行為明細点数", "行為明細薬剤料", "行為明細材料料", "出来高実績点数"]
        dfs['F'] = load_dpc_file(f_file, F_COLUMNS, numeric_cols=f_num)
        if dfs['F'] is not None: st.sidebar.success("✅ Fファイル 読込成功")

    if allocation_base_file:
        dfs['配賦基準マスタ'] = load_allocation_base_master(allocation_base_file)
        if dfs['配賦基準マスタ'] is not None: st.sidebar.success("✅ 配賦基準マスタ 読込成功")

    if med_file:
        dfs['医薬品マスタ'] = load_master_file(med_file, "医薬品マスタ")
        if dfs['医薬品マスタ'] is not None: st.sidebar.success("✅ 医薬品マスタ 読込成功")

    if mat_file:
        dfs['特定器材マスタ'] = load_master_file(mat_file, "特定器材マスタ")
        if dfs['特定器材マスタ'] is not None: st.sidebar.success("✅ 特定器材マスタ 読込成功")


    # --- 処理の実行条件（D, E, Fが揃っている時） ---
    if dfs.get('D') is not None and dfs.get('E') is not None and dfs.get('F') is not None:
        def_df = merge_and_calculate_patient_revenue(dfs)
            
        if def_df is not None:
            def_df = calculate_direct_costs(def_df, dfs)
            def_df = flag_patient_count_target(def_df, dfs)
            
            # ─── ② DPCデータから実在する部署一覧を抽出し、テンプレートCSVを生成 ───
            st.header("2. 部署別費用入力用テンプレートの生成")
            st.info("実在するDPCデータから部署一覧を抽出しました。以下のボタンからテンプレートをダウンロードし、収益・費用を記入してください。")
            
            dept_template_df = generate_department_template(def_df)
            template_csv = convert_df_to_csv(dept_template_df)
            
            st.download_button(
                label="📥 部署別費用マスタのテンプレートをダウンロード",
                data=template_csv,
                file_name="部署別費用マスタ_テンプレート.csv",
                mime="text/csv",
                key="download-dept-template"
            )
            
            with st.expander("抽出された部署マスタ（先頭プレビュー）"):
                st.dataframe(dept_template_df.head(15))
            
            # ─── ③ 次に、生成したテンプレートにユーザーが費用の金額を入力し、それをアップロードします ───
            st.header("3. 記入済み部署別費用マスタの取り込みと最終配賦")
            filled_dept_cost_file = st.file_uploader("記入済みの「部署別費用マスタ」をアップロードしてください (.csv)", type=["csv"])
            
            if filled_dept_cost_file:
                if "診療科区分" in def_df.columns:
                    max_len = def_df["診療科区分"].dropna().astype(str).str.strip().str.len().max()
                    if pd.isna(max_len) or max_len == 0:
                        max_len = 2
                else:
                    max_len = 2
                
                dfs['部署別費用マスタ'] = load_department_cost_master(filled_dept_cost_file, max_dept_len=int(max_len))
                
                if dfs['部署別費用マスタ'] is not None:
                    st.sidebar.success("✅ 記入済み部署別費用マスタ 読込成功")
                    
                    # 配賦計算の実行
                    def_df = allocate_indirect_costs(def_df, dfs)
                    
                    # ─── ④ 【損益計算（PL）集計結果】配賦をおこなって、損益計算書を作成する ───
                    st.header("4. 損益計算（PL）集計結果")
                    st.success("✅ すべての間接費用配賦が完了しました。")
                    
                    grand_total_revenue = def_df["収益"].sum()
                    grand_total_direct_cost = def_df["直接原価"].sum()
                    grand_total_indirect_cost = def_df["配賦間接費"].sum()
                    target_record_count = def_df["延べ患者カウント対象フラグ"].sum()
                    
                    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                    # with col_rx: のブロックをすべて削除し、直接記述
                    st.metric(label="💰 収益総額", value=f"{grand_total_revenue:,} 円")
                    st.metric(label="📦 直接原価合計", value=f"{grand_total_direct_cost:,} 円")
                    st.metric(label="🏛️ 配賦間接費合計", value=f"{grand_total_indirect_cost:,} 円")
                    st.metric(label="📋 延べ患者カウント総数", value=f"{target_record_count:,} 日")
                                            
                    st.markdown("##### 🔍 計算済データプレビュー（先頭5件）")
                    preview_cols = [
                        "データ識別番号", "入院年月日", "診療行為名称", "レセ電コード", 
                        "延べ患者カウント対象フラグ", "収益", "明細直接原価", "直接原価", "配賦間接費"
                    ]
                    st.dataframe(def_df[[col for col in preview_cols if col in def_df.columns]].head())

                    # ─── ⑤ 【配賦基準・単価の妥当性検証（監査用）】 ───
                    st.header("5. 配賦基準・単価の妥当性検証（監査用）")
                    st.markdown("配賦ロジックが正しく機能しているか、各部署の「延べ患者1人あたり単価」または「出来高1円あたり比率」で検証します。")

                    audit_rows = []
                    cost_master = dfs['部署別費用マスタ']

                    # ① 診療科部門の検証
                    dept1_costs = cost_master[cost_master["部門区分"] == "診療科"]
                    for _, row in dept1_costs.iterrows():
                        code = row["部署コード"]
                        cost = row["費用"]
                        name = row["部署名"]
                        mask = (def_df["延べ患者カウント対象フラグ"] == True) & (def_df["診療科区分"] == code)
                        denominator = mask.sum()
                        unit_price = cost / denominator if denominator > 0 else 0
                        audit_rows.append({
                            "部門区分": "① 診療科", "部署コード": code, "部署名": name, "総費用(円)": cost,
                            "分母（延べ患者数など）": f"{denominator:,} 日", "配賦単価・比率": f"{unit_price:,.1f} 円/日", "ステータス": "正常" if denominator > 0 or cost == 0 else "⚠️配賦対象(DPC)なし"
                        })

                    # ② 病棟部門の検証
                    dept2_costs = cost_master[cost_master["部門区分"] == "病棟"]
                    for _, row in dept2_costs.iterrows():
                        code = row["部署コード"]
                        cost = row["費用"]
                        name = row["部署名"]
                        actual_ward_code = code[1:] if code.startswith('B') else code
                        mask = (def_df["延べ患者カウント対象フラグ"] == True) & (def_df["病棟コード"] == actual_ward_code)
                        denominator = mask.sum()
                        unit_price = cost / denominator if denominator > 0 else 0
                        audit_rows.append({
                            "部門区分": "② 病棟", "部署コード": code, "部署名": name, "総費用(円)": cost,
                            "分母（延べ患者数など）": f"{denominator:,} 日", "配賦単価・比率": f"{unit_price:,.1f} 円/日", "ステータス": "正常" if denominator > 0 or cost == 0 else "⚠️配賦対象(DPC)なし"
                        })

                    # ③ 中央診療部門の検証
                    dept3_costs = cost_master[cost_master["部門区分"] == "中央診療"]
                    if len(dept3_costs) > 0 and '配賦基準マスタ' in dfs and dfs['配賦基準マスタ'] is not None:
                        base_master = dfs['配賦基準マスタ']
                        
                        points = pd.to_numeric(def_df["行為明細点数"], errors='coerce').fillna(0.0)
                        meds = pd.to_numeric(def_df["行為明細薬剤料"], errors='coerce').fillna(0.0)
                        mats = pd.to_numeric(def_df["行為明細材料料"], errors='coerce').fillna(0.0)
                        
                        def_df["temp_base_amount"] = points + meds + mats
                        
                        q_div = def_df["円・点区分"].astype(str).str.strip()
                        is_tensu = (q_div == "0") | (def_df["円・点区分"] == 0)
                        def_df.loc[is_tensu, "temp_base_amount"] = def_df.loc[is_tensu, "temp_base_amount"] * 10
                        
                        base_master_sub = base_master[base_master["部署コード"] != "999"].drop_duplicates(subset=["レセ電コード", "部署コード"])
                        target_lece_dict = {code: grp["レセ電コード"].unique() for code, grp in base_master_sub.groupby("部署コード")}
                        
                        for _, row in dept3_costs.iterrows():
                            code = row["部署コード"]
                            cost = row["費用"]
                            name = row["部署名"]
                            
                            target_leces = target_lece_dict.get(code, [])
                            mask = def_df["レセ電コード"].isin(target_leces)
                            denominator = def_df.loc[mask, "temp_base_amount"].sum() if mask.any() else 0
                            unit_price = cost / denominator if denominator > 0 else 0
                            
                            audit_rows.append({
                                "部門区分": "③ 中央診療", 
                                "部署コード": code, 
                                "部署名": name, 
                                "総費用(円)": cost,
                                "分母（延べ患者数など）": f"{denominator:,.0f} 円", 
                                "配賦単価・比率": f"{unit_price:,.3f} 円/円", 
                                "ステータス": "正常" if denominator > 0 or cost == 0 else "⚠️配賦対象(DPC)なし"
                            })
                        def_df = def_df.drop(columns=["temp_base_amount"])

                    # ④ その他部門の検証
                    dept4_costs = cost_master[cost_master["部門区分"] == "その他"]
                    total_other_cost = dept4_costs["費用"].sum()
                    if total_other_cost > 0:
                        mask = (def_df["延べ患者カウント対象フラグ"] == True)
                        denominator = mask.sum()
                        unit_price = total_other_cost / denominator if denominator > 0 else 0
                        audit_rows.append({
                            "部門区分": "④ その他", "部署コード": "9999", "部署名": "共通管理費", "総費用(円)": total_other_cost,
                            "分母（延べ患者数など）": f"{denominator:,} 日", "配賦単価・比率": f"{unit_price:,.1f} 円/日", "ステータス": "正常" if denominator > 0 else "⚠️配賦対象(DPC)なし"
                        })

                    audit_df = pd.DataFrame(audit_rows)
                    st.dataframe(audit_df, use_container_width=True, hide_index=True)
                    
                    has_warning = audit_df["ステータス"].str.contains("⚠️").any()
                    if has_warning:
                        st.warning("💡 【注意】DPCデータ側に該当するコードの実績が存在しないため、費用を配賦できなかった部署（0除算回避）があります。マスタのコード設定や、対象期間のデータをご確認ください。")
                    else:
                        st.success("✨ 【確認完了】すべての対象部署において、分母（実績データ）が存在し、ロジック通り正常に按分・配賦されています。")
                    
                    # ─── ⑥ 【最終データの検証・出力】 ───
                    st.header("6. 最終データの検証・出力")
                    with st.spinner("ダウンロード用ファイルの準備中..."):
                        csv_data = convert_df_to_csv(def_df)
                    
                    st.download_button(
                        label="📥 全計算済のDEF結合データをCSVでダウンロード",
                        data=csv_data,
                        file_name="def_merged_full_calculated.csv",
                        mime="text/csv",
                        key="download-def-csv-final"
                    )


if __name__ == "__main__":
    main()
