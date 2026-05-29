import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

RAW_SHEET = "title groups"
KAPPA_SHEET = "title_kappa"

DATA_PATH = "title 用于 app数据.csv"
SPREADSHEET_ID = "1VeGdUjuje836LwdghDEZ_F43zIy5Ey9unJQC_X05JMQ"

OPTIONS = [
    "1. Obesity mentioned",
    "2. About health",
    "3. About weight loss",
    "4. About Weight loss medicine",
    "5. About Diet or food",
    "6. About body image",
    "7. About other disease",
    "8. About policy",
    "9. Ambiguous",
    "10. Irrelevant"
]

RAW_HEADER = [
    "coder_id",
    "title_id",
    "s_col",
    "title",
    "question",
    "answer",
    "comment",
    "updated_at"
]

st.set_page_config(page_title="Study 3 Title Grouping", layout="wide")
st.title("Study 3 Title Grouping")


def norm_id(x):
    x = str(x).strip()
    if x.endswith(".0"):
        x = x[:-2]
    return x


@st.cache_data
def load_questions_from_csv(file_path):
    df = pd.read_csv(file_path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    required_cols = ["New ID", "Title"]

    for col in required_cols:
        if col not in df.columns:
            st.error(f"CSV 文件缺少必要列：{col}")
            st.stop()

    pages = []

    for _, row in df.iterrows():
        title_id = norm_id(row["New ID"])
        title_text = str(row["Title"]).strip()

        if title_id == "" or title_text == "" or title_text.lower() == "nan":
            continue

        pages.append({
            "title_id": title_id,
            "title": title_text,
            "sub_questions": [
                {
                    "s_col": "TITLE",
                    "text": title_text
                }
            ]
        })

    return pages


@st.cache_resource
def connect_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes
    )

    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID)
    return sheet


@st.cache_resource
def get_cached_ws(name, rows=1000, cols=50):
    sheet = connect_sheet()
    try:
        return sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=name, rows=rows, cols=cols)
        if name == RAW_SHEET:
            ws.update([RAW_HEADER])
        else:
            ws.update([["title_id", "s_col", "question"]])
        return ws


def ensure_raw_header(raw_ws):
    values = raw_ws.get_all_values()

    if not values:
        raw_ws.update([RAW_HEADER])
        return

    current_header = values[0]

    if current_header != RAW_HEADER:
        raw_ws.update("A1:H1", [RAW_HEADER])


@st.cache_data(ttl=60)
def read_raw_data_cached():
    raw_ws = get_cached_ws(RAW_SHEET)
    ensure_raw_header(raw_ws)

    values = raw_ws.get_all_values()

    if len(values) <= 1:
        df = pd.DataFrame(columns=RAW_HEADER)
        df["_row_num"] = []
        return df

    header = values[0]
    rows = values[1:]

    df = pd.DataFrame(rows, columns=header)

    for col in RAW_HEADER:
        if col not in df.columns:
            df[col] = ""

    df = df[RAW_HEADER]
    df = df.fillna("")
    df["_row_num"] = range(2, len(df) + 2)

    df["coder_id"] = df["coder_id"].astype(str).str.strip().str.lower()
    df["title_id"] = df["title_id"].apply(norm_id)
    df["s_col"] = df["s_col"].astype(str).str.strip()

    return df


def clear_raw_cache():
    read_raw_data_cached.clear()


def save_page_responses_fast(
    raw_ws,
    coder_id,
    title_id,
    title,
    responses,
    comment
):
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 保存前读一次最新表格，保证新答案覆盖旧答案
    values = raw_ws.get_all_values()

    if len(values) <= 1:
        live_df = pd.DataFrame(columns=RAW_HEADER)
        live_df["_row_num"] = []
    else:
        header = values[0]
        rows = values[1:]
        live_df = pd.DataFrame(rows, columns=header)

        for col in RAW_HEADER:
            if col not in live_df.columns:
                live_df[col] = ""

        live_df = live_df[RAW_HEADER]
        live_df = live_df.fillna("")
        live_df["_row_num"] = range(2, len(live_df) + 2)

        live_df["coder_id"] = live_df["coder_id"].astype(str).str.strip().str.lower()
        live_df["title_id"] = live_df["title_id"].apply(norm_id)
        live_df["s_col"] = live_df["s_col"].astype(str).str.strip()

    coder_id = str(coder_id).strip().lower()
    title_id = norm_id(title_id)

    existing = live_df[
        (live_df["coder_id"].astype(str) == coder_id) &
        (live_df["title_id"].astype(str) == title_id)
    ]

    updates = []
    append_rows = []

    for item in responses:
        s_col = str(item["s_col"]).strip()

        row_values = [
            coder_id,
            title_id,
            s_col,
            title,
            item["question"],
            item["answer"],
            comment,
            updated_at
        ]

        matched = existing[
            existing["s_col"].astype(str).str.strip() == s_col
        ]

        if not matched.empty:
            row_num = int(matched.iloc[-1]["_row_num"])
            updates.append({
                "range": f"A{row_num}:H{row_num}",
                "values": [row_values]
            })
        else:
            append_rows.append(row_values)

    if updates:
        raw_ws.batch_update(updates)

    if append_rows:
        raw_ws.append_rows(append_rows, value_input_option="USER_ENTERED")

    clear_raw_cache()


def update_kappa_format(kappa_ws, df):
    kappa_ws.clear()

    if df.empty:
        kappa_ws.update([["title_id", "s_col", "question"]])
        return

    df = df.copy().fillna("")

    if "_row_num" in df.columns:
        df = df.drop(columns=["_row_num"])

    df = df.sort_values("updated_at")
    df = df.drop_duplicates(
        subset=["coder_id", "title_id", "s_col"],
        keep="last"
    )

    wide = df.pivot_table(
        index=["title_id", "s_col", "question"],
        columns="coder_id",
        values="answer",
        aggfunc="first"
    ).reset_index()

    wide.columns.name = None
    wide = wide.fillna("")
    wide = wide.sort_values(["title_id", "s_col"])

    kappa_ws.update(
        [wide.columns.tolist()] + wide.astype(str).values.tolist()
    )


PAGES = load_questions_from_csv(DATA_PATH)

if len(PAGES) == 0:
    st.error("CSV 中没有可用题目。请检查 New ID 和 Title 是否有内容。")
    st.stop()

raw_ws = get_cached_ws(RAW_SHEET)
kappa_ws = get_cached_ws(KAPPA_SHEET)

df = read_raw_data_cached()

coder = st.text_input(
    "请输入你的 coder ID：",
    placeholder="例如 CoderA / CoderB / CoderC"
)

if not coder:
    st.info("请输入 coder ID 后开始。")
    st.stop()

coder = coder.strip().lower()

st.write(f"Current coder: {coder}")
st.info(
    "点击“保存并下一题”会自动保存本页答案。"
    "下次输入同一个 coder ID，会自动回到你上次停止的位置。"
)

coder_df = df[df["coder_id"].astype(str) == coder].copy()

if not coder_df.empty:
    coder_df = coder_df.sort_values("_row_num")
    completed_title_ids = set(coder_df["title_id"].astype(str).apply(norm_id).tolist())
else:
    completed_title_ids = set()

total = len(PAGES)
done = len(completed_title_ids)

st.progress(done / total if total > 0 else 0)
st.write(f"进度：{done}/{total}")

if "current_coder" not in st.session_state or st.session_state.current_coder != coder:
    st.session_state.current_coder = coder
    st.session_state.finished = False

    first_incomplete_index = None

    for i, page in enumerate(PAGES):
        if norm_id(page["title_id"]) not in completed_title_ids:
            first_incomplete_index = i
            break

    if first_incomplete_index is None:
        st.session_state.current_index = total - 1
        st.session_state.finished = True
    else:
        st.session_state.current_index = first_incomplete_index

if "current_index" not in st.session_state:
    st.session_state.current_index = 0

if st.session_state.finished:
    st.success("所有标题已经完成。谢谢参与！")
    st.balloons()

    st.divider()
    if st.button("更新 title_kappa 表"):
        latest_df = read_raw_data_cached()
        update_kappa_format(kappa_ws, latest_df)
        st.success("title_kappa 已更新。")

    st.stop()

idx = st.session_state.current_index
idx = max(0, min(idx, len(PAGES) - 1))
st.session_state.current_index = idx

page = PAGES[idx]

title_id = norm_id(page["title_id"])
title_text = page["title"]
sub_questions = page["sub_questions"]

st.divider()
st.subheader(f"Title {idx + 1} of {total}")
st.write(f"**New ID:** {title_id}")

st.markdown("### 标题")
st.write(title_text)

st.markdown("### 请判断这个标题属于哪个选项")

existing_page_answers = df[
    (df["coder_id"].astype(str) == coder) &
    (df["title_id"].astype(str).apply(norm_id) == title_id)
].copy()

if not existing_page_answers.empty:
    existing_page_answers = existing_page_answers.sort_values("_row_num")

existing_answer_dict = {}
existing_comment = ""

for _, row in existing_page_answers.iterrows():
    existing_answer_dict[str(row["s_col"]).strip()] = str(row["answer"]).strip()
    if str(row.get("comment", "")).strip() != "":
        existing_comment = str(row.get("comment", "")).strip()

responses = []

for sub_q in sub_questions:
    s_col = sub_q["s_col"]
    q_text = sub_q["text"]

    st.divider()

    full_question = f"这个标题：{q_text} 属于下面哪个选项？"
    st.write(full_question)

    default_answer = existing_answer_dict.get(s_col, "")

    radio_key = f"{coder}_{idx}_{s_col}"

    if radio_key not in st.session_state:
        if default_answer in OPTIONS:
            st.session_state[radio_key] = default_answer

    answer = st.radio(
        label=f"{s_col}_answer",
        options=OPTIONS,
        key=radio_key,
        label_visibility="collapsed"
    )

    responses.append({
        "s_col": s_col,
        "question": full_question,
        "answer": answer
    })

comment_key = f"{coder}_{idx}_comment"

if comment_key not in st.session_state:
    st.session_state[comment_key] = existing_comment

comment = st.text_area(
    "本页备注（可选）：",
    key=comment_key
)

st.divider()

nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 1])

with nav_col1:
    if st.button("⬅️ 保存并上一题"):
        save_page_responses_fast(
            raw_ws=raw_ws,
            coder_id=coder,
            title_id=title_id,
            title=title_text,
            responses=responses,
            comment=comment
        )

        if st.session_state.current_index > 0:
            st.session_state.current_index -= 1

        st.session_state.finished = False
        st.rerun()

with nav_col2:
    jump_to = st.number_input(
        "跳转到第几题：",
        min_value=1,
        max_value=total,
        value=idx + 1,
        step=1
    )

    if st.button("保存并跳转"):
        save_page_responses_fast(
            raw_ws=raw_ws,
            coder_id=coder,
            title_id=title_id,
            title=title_text,
            responses=responses,
            comment=comment
        )

        st.session_state.current_index = int(jump_to) - 1
        st.session_state.finished = False
        st.rerun()

with nav_col3:
    button_label = "完成" if st.session_state.current_index == len(PAGES) - 1 else "保存并下一题 ➡️"

    if st.button(button_label):
        save_page_responses_fast(
            raw_ws=raw_ws,
            coder_id=coder,
            title_id=title_id,
            title=title_text,
            responses=responses,
            comment=comment
        )

        if st.session_state.current_index < len(PAGES) - 1:
            st.session_state.current_index += 1
        else:
            st.session_state.finished = True

        st.rerun()

st.divider()
st.subheader("Google Sheets 状态")

st.write("答案会自动保存到 Google Sheets。")
st.write("title groups = 原始长表，每一行是一个 coder 对一个标题的判断。")
st.write("title_kappa = 可用于计算 kappa 的宽表。")

if st.button("手动更新 title_kappa 表"):
    latest_df = read_raw_data_cached()
    update_kappa_format(kappa_ws, latest_df)
    st.success("title_kappa 已更新。")
