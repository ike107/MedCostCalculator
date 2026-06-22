import pandas as pd
import streamlit as st

# ==========================================
# [2] FILE_DEFINITIONS_AND_SCHEMAS (列定義)
# ==========================================

D_COLUMNS = [
    "施設コード", "データ識別番号", "退院年月日", "入院年月日", "データ区分", "順序番号",
    "病院点数マスターコード", "レセ電コード", "解釈番号", "診療行為名称", "行為点数",
    "行為薬剤料", "行為材料料", "円点区分", "行為回数", "保険者番号", "レセプト種別コード",
    "実施年月日", "レセプト科区分", "診療科区分", "医師コード", "病棟コード", "病棟区分",
    "入外区分", "施設タイプ", "算定開始日", "算定終了日", "算定起算日", "分類番号", "医療機関関係数"
]

E_COLUMNS = [
    "施設コード", "データ識別番号", "退院年月日", "入院年月日", "データ区分", "順序番号",
    "病院点数マスターコード", "レセ電コード", "解釈番号", "診療行為名称", "行為点数",
    "行為薬剤料", "行為材料料", "円点区分", "行為回数", "保険者番号", "レセプト種別コード",
    "実施年月日", "レセプト科区分", "診療科区分", "医師コード", "病棟コード", "病棟区分",
    "入外区分", "施設タイプ"
]

F_COLUMNS = [
    "施設コード", "データ識別番号", "退院年月日", "入院年月日", "データ区分", "順序番号",
    "行為明細番号", "病院点数マスターコード", "レセ電コード", "解釈番号", "診療行為名称",
    "使用量", "基準単位", "行為明細点数", "行為明細薬剤料", "行為明細材料料", "円・点区分",
    "出来高実績点数", "行為明細区分情報"
]

# 中央診療部門のデフォルトマスタ定義
CHUO_DEFAULTS = [
    {"部門区分": "中央診療", "部署コード": "3101", "デフォルト部署名": "手術"},
    {"部門区分": "中央診療", "部署コード": "3102", "デフォルト部署名": "麻酔"},
    {"部門区分": "中央診療", "部署コード": "3103", "デフォルト部署名": "検査"},
    {"部門区分": "中央診療", "部署コード": "3104", "デフォルト部署名": "画像診断"},
    {"部門区分": "中央診療", "部署コード": "3105", "デフォルト部署名": "リハビリ"},
    {"部門区分": "中央診療", "部署コード": "3106", "デフォルト部署名": "透析"},
    {"部門区分": "中央診療", "部署コード": "3201", "デフォルト部署名": "材料薬剤"},
    {"部門区分": "中央診療", "部署コード": "3202", "デフォルト部署名": "材料"},
    {"部門区分": "中央診療", "部署コード": "3203", "デフォルト部署名": "薬剤"},
    {"部門区分": "中央診療", "部署コード": "3204", "デフォルト部署名": "栄養"},
]

# ==========================================
# データファイル読み込み関数群
# ==========================================

def load_dpc_file(file, columns_def, numeric_cols=None):
    try:
        df = pd.read_csv(file, sep='\t', header=None, encoding='cp932', names=columns_def, dtype=str)
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
        if numeric_cols:
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        st.error(f"DPCファイルの読み込み中にエラーが発生しました: {e}")
        return None


def load_master_file(file, master_name):
    try:
        df = pd.read_csv(
            file, sep=',', header=None, encoding='cp932', 
            usecols=[2, 11], names=["レセ電コード", "償還価格"], dtype={"レセ電コード": str}
        )
        df["レセ電コード"] = df["レセ電コード"].astype(str).str.strip()
        df["償還価格"] = pd.to_numeric(df["償還価格"], errors='coerce')
        return df
    except Exception as e:
        st.error(f"{master_name}の読み込み中にエラーが発生しました: {e}")
        return None


def load_allocation_base_master(file):
    """配賦基準マスタ(.tab)を読み込む（文字コード自動フォールバック付き）"""
    try:
        df = pd.read_csv(
            file, sep='\t', header=None, encoding='cp932',
            usecols=[6, 8, 10], names=["部署コード", "部門コード", "レセ電コード"],
            dtype=str
        )
    except UnicodeDecodeError:
        file.seek(0)
        try:
            df = pd.read_csv(
                file, sep='\t', header=None, encoding='utf_8_sig',
                usecols=[6, 8, 10], names=["部署コード", "部門コード", "レセ電コード"],
                dtype=str
            )
        except Exception as e:
            st.error(f"配賦基準マスタの読み込み中に文字コードエラーが発生しました: {e}")
            return None
    except Exception as e:
        st.error(f"配賦基準マスタの読み込み中に予期せぬエラーが発生しました: {e}")
        return None

    df["部署コード"] = df["部署コード"].astype(str).str.strip()
    df["部門コード"] = df["部門コード"].astype(str).str.strip()
    df["レセ電コード"] = df["レセ電コード"].astype(str).str.strip()
    return df


def load_department_cost_master(file, max_dept_len=2):
    """
    【ゼロ落ち修正版】ユーザーが記入してアップロードした部署別費用マスタ(.csv)を読み込む
    Excel等で保存した際に消えてしまった先頭の「0（ゼロ落ち）」を、DPCデータ本来の桁数に合わせて自動復元します。
    """
    try:
        # まずは本来の想定である cp932 で試みる
        df = pd.read_csv(file, sep=',', encoding='cp932', dtype=str) # すべて一旦文字列として読み込む
    except UnicodeDecodeError:
        file.seek(0)
        try:
            df = pd.read_csv(file, sep=',', encoding='utf_8_sig', dtype=str)
        except Exception as e:
            st.error(f"部署別費用マスタの読み込み中に文字コードエラーが発生しました: {e}")
            return None
    except Exception as e:
        st.error(f"部署別費用マスタの読み込み中に予期せぬエラーが発生しました: {e}")
        return None

    # 文字列のクレンジングと、消えた「0」の自動補正
    try:
        df["部門区分"] = df["部門区分"].astype(str).str.strip()
        df["部署コード"] = df["部署コード"].astype(str).str.strip()
        df["部署名"] = df["部署名"].astype(str).str.strip().fillna("")
        
        # ⭐【重要】ゼロ落ちの自動復元処理
        # 部門区分が「診療科」のものに対してのみ、DPCデータの本来の桁数（max_dept_len）になるように先頭を '0' で埋める
        is_shinjyoka = df["部門区分"] == "診療科"
        df.loc[is_shinjyoka, "部署コード"] = df.loc[is_shinjyoka, "部署コード"].apply(lambda x: x.zfill(max_dept_len) if x.isdigit() else x)
        
        # 数値列の変換
        df["収益"] = pd.to_numeric(df["収益"], errors='coerce').fillna(0)
        df["費用"] = pd.to_numeric(df["費用"], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"部署別費用マスタのデータ加工中にエラーが発生しました: {e}")
        return None


# ==========================================
# 結合処理 兼 患者単位収益集約ロジック
# ==========================================

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


# ==========================================
# 直接原価計算 ロジック
# ==========================================

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
        
        f_use = pd.to_numeric(merged_df["使用量"], errors='coerce').fillna(0.0)
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


# ==========================================
# 延べ患者フラグ付与（部署コード999判定）
# ==========================================

def flag_patient_count_target(merged_df, dfs_dict):
    with st.spinner("配賦基準マスタ（部署コード999）に基づく延べ患者判定中..."):
        if '配賦基準マスタ' in dfs_dict and dfs_dict['配賦基準マスタ'] is not None:
            base_master = dfs_dict['配賦基準マスタ']
            total_pt_codes = set(base_master.loc[base_master["部署コード"] == "999", "レセ電コード"].dropna().unique())
            merged_df["延べ患者カウント対象フラグ"] = merged_df["レセ電コード"].isin(total_pt_codes)
        else:
            merged_df["延べ患者カウント対象フラグ"] = False
            
        return merged_df


# ==========================================
# 【新設】部署マスタ（テンプレート）生成ロジック
# ==========================================

def generate_department_template(df):
    """DPCデータから実在する部署を抽出し、中央診療・その他を統合した空のテンプレートCSVを作成する"""
    rows = []
    
    # 1. 診療科区分の抽出 (空文字・NaNを除外)
    if "診療科区分" in df.columns:
        valid_dept = df["診療科区分"].dropna().unique()
        for d in valid_dept:
            d_str = str(d).strip()
            if d_str and d_str != "nan":
                rows.append({"部門区分": "診療科", "部署コード": d_str, "部署名": ""})
                
    # 2. 病棟コードの抽出 (空文字・NaNを除外、先頭に'B'を付与)
    if "病棟コード" in df.columns:
        valid_wards = df["病棟コード"].dropna().unique()
        for w in valid_wards:
            w_str = str(w).strip()
            if w_str and w_str != "nan":
                rows.append({"部門区分": "病棟", "部署コード": f"B{w_str}", "部署名": ""})
                
    # データフレーム化し、重複を排除
    template_df = pd.DataFrame(rows).drop_duplicates(subset=["部門区分", "部署コード"])
    
    # 3. 中央診療部門（デフォルトマスタ）を合流
    chuo_df = pd.DataFrame(CHUO_DEFAULTS)
    chuo_df.rename(columns={"デフォルト部署名": "部署名"}, inplace=True)
    template_df = pd.concat([template_df, chuo_df], ignore_index=True)
    
    # 4. その他部門（コード9999）を合流
    other_row = pd.DataFrame([{"部門区分": "その他", "部署コード": "9999", "部署名": "共通管理費"}])
    template_df = pd.concat([template_df, other_row], ignore_index=True)
    
    # ユーザー記入用の「収益」と「費用」列を空欄（0）で作成
    template_df["収益"] = 0
    template_df["費用"] = 0
    
    return template_df


# ==========================================
# [4-4] INDIRECT_COST_ALLOCATION (間接費用配賦メインロジック)
# ==========================================

def allocate_indirect_costs(df, dfs_dict):
    if '部署別費用マスタ' not in dfs_dict or dfs_dict['部署別費用マスタ'] is None:
        df["配賦間接費"] = 0
        return df

    cost_master = dfs_dict['部署別費用マスタ'].copy()
    base_master = dfs_dict['配賦基準マスタ'].copy() if '配賦基準マスタ' in dfs_dict else None
    
    df["allocated_cost_internal"] = 0.0
    
    with st.spinner("間接費用の配賦（按分）計算を実行中..."):
        # ① 診療科部門 の配賦 (費用を配賦)
        dept1_costs = cost_master[cost_master["部門区分"] == "診療科"]
        for _, row in dept1_costs.iterrows():
            code = row["部署コード"]
            cost = row["費用"]  # 費用列を参照
            if cost == 0: continue
            mask = (df["延べ患者カウント対象フラグ"] == True) & (df["診療科区分"] == code)
            denominator = mask.sum()
            if denominator > 0:
                df.loc[mask, "allocated_cost_internal"] += (cost / denominator)
                
        # ② 病棟部門 の配賦 (費用を配賦、DPC側はBを外して紐付け)
        dept2_costs = cost_master[cost_master["部門区分"] == "病棟"]
        for _, row in dept2_costs.iterrows():
            code = row["部署コード"]
            cost = row["費用"]
            if cost == 0: continue
            # マスタ側は 'B100'、DPC側は '100' なので、先頭の'B'を除去して比較
            actual_ward_code = code[1:] if code.startswith('B') else code
            mask = (df["延べ患者カウント対象フラグ"] == True) & (df["病棟コード"] == actual_ward_code)
            denominator = mask.sum()
            if denominator > 0:
                df.loc[mask, "allocated_cost_internal"] += (cost / denominator)

       # ③ 中央診療部門 の配賦
        dept3_costs = cost_master[cost_master["部門区分"] == "中央診療"]
        if len(dept3_costs) > 0 and base_master is not None:
            
            # 1. 各項目を数値化して単純に合算（ベース金額）
            points = pd.to_numeric(df["行為明細点数"], errors='coerce').fillna(0.0)
            meds = pd.to_numeric(df["行為明細薬剤料"], errors='coerce').fillna(0.0)
            mats = pd.to_numeric(df["行為明細材料料"], errors='coerce').fillna(0.0)
            df["temp_base_amount"] = points + meds + mats
            
            # 2. 円・点区分（Q列）をきれいにクリーニング
            q_div = df["円・点区分"].astype(str).str.strip()
            
            # 💡 【修正】「0」（点数単位）の行だけを狙い撃ちして10倍（円換算）にする
            # 空白やNaNが「0」と判定されないよう、明示的に文字列の"0"または数値の0を判定
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


@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf_8_sig')


# ==========================================
# Streamlitアプリメイン処理
# ==========================================

def main():
    st.title("DPCデータ 損益計算（PL）ダッシュボード")
    
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


    # --- 処理の実行 ---
    if dfs.get('D') is not None and dfs.get('E') is not None and dfs.get('F') is not None:
        def_df = merge_and_calculate_patient_revenue(dfs)
            
        if def_df is not None:
            def_df = calculate_direct_costs(def_df, dfs)
            def_df = flag_patient_count_target(def_df, dfs)
            
            # ---------------------------------------------------------
            # ⭐【新要件】部署マスタテンプレートの自動生成とダウンロード
            # ---------------------------------------------------------
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
            
            # プレビュー表示
            with st.expander("抽出された部署マスタ（先頭プレビュー）"):
                st.dataframe(dept_template_df.head(15))
            
            # ---------------------------------------------------------
            # ⭐【新要件】記入済みマスタのアップロードと最終配賦計算
            # ---------------------------------------------------------
            st.header("3. 記入済み部署別費用マスタの取り込みと最終配賦")
            filled_dept_cost_file = st.file_uploader("記入済みの「部署別費用マスタ」をアップロードしてください (.csv)", type=["csv"])
            
            if filled_dept_cost_file:
                # DPCデータ（def_df）に存在する本来の「診療科区分」の最大桁数を自動取得（例: "010"なら3桁）
                if "診療科区分" in def_df.columns:
                    max_len = def_df["診療科区分"].dropna().astype(str).str.strip().str.len().max()
                    if pd.isna(max_len) or max_len == 0:
                        max_len = 2 # デフォルト
                else:
                    max_len = 2
                
                # 割り出した最大桁数を引数に渡して読み込む
                dfs['部署別費用マスタ'] = load_department_cost_master(filled_dept_cost_file, max_dept_len=int(max_len))
                
                if dfs['部署別費用マスタ'] is not None:
                    st.sidebar.success("✅ 記入済み部署別費用マスタ 読込成功")
                    
                    # 配賦計算の実行
                    def_df = allocate_indirect_costs(def_df, dfs)
                    
                    st.header("4. 損益計算（PL）集計結果")
                    st.success("✅ すべての間接費用配賦が完了しました。")
                    
                    # 画面表示用の集計
                    grand_total_revenue = def_df["収益"].sum()
                    grand_total_direct_cost = def_df["直接原価"].sum()
                    grand_total_indirect_cost = def_df["配賦間接費"].sum()
                    target_record_count = def_df["延べ患者カウント対象フラグ"].sum()
                    
                    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                    with col_r1:
                        st.metric(label="💰 収益総額", value=f"{grand_total_revenue:,} 円")
                    with col_r2:
                        st.metric(label="📦 直接原価合計", value=f"{grand_total_direct_cost:,} 円")
                    with col_r3:
                        st.metric(label="🏛️ 配賦間接費合計", value=f"{grand_total_indirect_cost:,} 円")
                    with col_r4:
                        st.metric(label="📋 延べ患者カウント総数", value=f"{target_record_count:,} 日")
                        
                    # データの検証・出力機能
                    st.markdown("##### 🔍 最終データの検証・出力")
                    with st.spinner("ダウンロード用ファイルの準備中..."):
                        csv_data = convert_df_to_csv(def_df)
                    
                    st.download_button(
                        label="📥 全計算済のDEF結合データをCSVでダウンロード",
                        data=csv_data,
                        file_name="def_merged_full_calculated.csv",
                        mime="text/csv",
                        key="download-def-csv"
                    )
                    
                    st.markdown("---")
                    st.markdown("##### 計算済データプレビュー（先頭5件）")
                    preview_cols = [
                        "データ識別番号", "入院年月日", "診療行為名称", "レセ電コード", 
                        "延べ患者カウント対象フラグ", "収益", "明細直接原価", "直接原価", "配賦間接費"
                    ]
                    st.dataframe(def_df[[col for col in preview_cols if col in def_df.columns]].head())

                    # ─── 【新設】ここから検証・監査用ロジックと画面表示 ───
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
                        
                        # 💡 【修正】監査側も「0」の場合に10倍するロジックに同期
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

                    # 検証用テーブルを表示
                    audit_df = pd.DataFrame(audit_rows)
                    st.dataframe(audit_df, use_container_width=True, hide_index=True)
                    
                    # ⚠️警告ステータスがある場合の通知
                    has_warning = audit_df["ステータス"].str.contains("⚠️").any()
                    if has_warning:
                        st.warning("💡 【注意】DPCデータ側に該当するコードの実績が存在しないため、費用を配賦できなかった部署（0除算回避）があります。マスタのコード設定や、対象期間のデータをご確認ください。")
                    else:
                        st.success("✨ 【確認完了】すべての対象部署において、分母（実績データ）が存在し、ロジック通り正常に按分・配賦されています。")
                    # ─── 【新設】ここまで ───
                    
                    
                    # ⚠️ 以下の「最終データの検証・出力」パートは既存のコードと地続きになります
                    st.header("6. 最終データの検証・出力")
                    with st.spinner("ダウンロード用ファイルの準備中..."):
                        csv_data = convert_df_to_csv(def_df)
                    
                    # 💡 コードの最下部付近（旧613行目あたり）のボタンです
                    st.download_button(
                        label="📥 全計算済のDEF結合データをCSVでダウンロード",
                        data=csv_data,
                        file_name="def_merged_full_calculated.csv",
                        mime="text/csv",
                        key="download-def-csv-final"  # ← ここを -final に修正
                    )
                    
                    st.markdown("---")
                    st.markdown("##### 計算済データプレビュー（先頭5件）")
                    preview_cols = [
                        "データ識別番号", "入院年月日", "診療行為名称", "レセ電コード", 
                        "延べ患者カウント対象フラグ", "収益", "明細直接原価", "直接原価", "配賦間接費"
                    ]
                    st.dataframe(def_df[[col for col in preview_cols if col in def_df.columns]].head())


if __name__ == "__main__":
    main()