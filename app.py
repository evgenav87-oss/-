import streamlit as st
import pandas as pd
import plotly.express as px
import pulp

st.set_page_config(page_title="Energy Optimizer", page_icon="⚡", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; max-width: 1250px;}
h1 {letter-spacing: -0.03em;}
[data-testid="stMetric"] {background: rgba(120,120,120,.07); padding: 14px; border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

st.title("⚡ Energy Optimizer")
st.caption("Математичне планування використання обмеженого запасу електроенергії під час відключень")

with st.sidebar:
    st.header("Параметри системи")
    battery_wh = st.number_input("Номінальна ємність акумулятора, Вт·год", min_value=50, max_value=20000, value=500, step=50)
    efficiency = st.slider("ККД системи, %", min_value=50, max_value=100, value=90)
    reserve = st.slider("Недоторканний резерв заряду, %", min_value=0, max_value=50, value=10)
    outage_hours = st.slider("Тривалість відключення, год", min_value=1, max_value=24, value=8)
    inverter_w = st.number_input("Максимальна потужність інвертора, Вт", min_value=50, max_value=10000, value=300, step=50)
    st.divider()
    st.caption("Модель використовує часові інтервали тривалістю 1 година.")

available_wh = battery_wh * efficiency / 100 * (1 - reserve / 100)

st.subheader("1. Перелік електроприладів")
st.write("Змініть приклади або додайте власні прилади. Пріоритет: 5 — критично важливий, 1 — найменш важливий.")
initial = pd.DataFrame([
    {"Прилад": "Wi-Fi роутер", "Потужність, Вт": 10, "Потрібно годин": 8, "Пріоритет": 5, "Початок вікна": 0, "Кінець вікна": 8},
    {"Прилад": "LED освітлення", "Потужність, Вт": 20, "Потрібно годин": 5, "Пріоритет": 5, "Початок вікна": 17, "Кінець вікна": 24},
    {"Прилад": "Ноутбук", "Потужність, Вт": 65, "Потрібно годин": 3, "Пріоритет": 3, "Початок вікна": 8, "Кінець вікна": 22},
    {"Прилад": "Холодильник (усереднено)", "Потужність, Вт": 35, "Потрібно годин": 8, "Пріоритет": 5, "Початок вікна": 0, "Кінець вікна": 8},
    {"Прилад": "Телевізор", "Потужність, Вт": 80, "Потрібно годин": 2, "Пріоритет": 1, "Початок вікна": 18, "Кінець вікна": 24},
])
if "devices" not in st.session_state:
    st.session_state.devices = initial

edited = st.data_editor(
    st.session_state.devices,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Прилад": st.column_config.TextColumn(required=True),
        "Потужність, Вт": st.column_config.NumberColumn(min_value=1, max_value=10000, step=1, required=True),
        "Потрібно годин": st.column_config.NumberColumn(min_value=0, max_value=24, step=1, required=True),
        "Пріоритет": st.column_config.NumberColumn(min_value=1, max_value=5, step=1, required=True),
        "Початок вікна": st.column_config.NumberColumn(min_value=0, max_value=23, step=1, required=True),
        "Кінець вікна": st.column_config.NumberColumn(min_value=1, max_value=24, step=1, required=True),
    },
    key="device_editor"
)
st.session_state.devices = edited

valid = True
errors = []
if edited.empty:
    valid = False
    errors.append("Додайте хоча б один електроприлад.")
for idx, row in edited.iterrows():
    if not str(row["Прилад"]).strip():
        valid = False
        errors.append(f"Рядок {idx+1}: вкажіть назву приладу.")
    if pd.isna(row["Потужність, Вт"]) or row["Потужність, Вт"] <= 0:
        valid = False
        errors.append(f"Рядок {idx+1}: потужність має бути більшою за нуль.")
    if pd.isna(row["Потрібно годин"]) or row["Потрібно годин"] < 0 or row["Потрібно годин"] > outage_hours:
        valid = False
        errors.append(f"Рядок {idx+1}: потрібна кількість годин має бути від 0 до тривалості відключення.")
    if pd.isna(row["Пріоритет"]) or not 1 <= row["Пріоритет"] <= 5:
        valid = False
        errors.append(f"Рядок {idx+1}: пріоритет має бути від 1 до 5.")
    if pd.isna(row["Початок вікна"]) or pd.isna(row["Кінець вікна"]) or not (0 <= row["Початок вікна"] < row["Кінець вікна"] <= 24):
        valid = False
        errors.append(f"Рядок {idx+1}: часовий інтервал має задовольняти 0 ≤ початок < кінець ≤ 24.")

for e in errors:
    st.error(e)

requested_wh = 0.0
if not edited.empty and "Потужність, Вт" in edited and "Потрібно годин" in edited:
    requested_wh = sum(float(r["Потужність, Вт"]) * float(r["Потрібно годин"]) for _, r in edited.iterrows() if pd.notna(r["Потужність, Вт"]) and pd.notna(r["Потрібно годин"]))

m1, m2, m3 = st.columns(3)
m1.metric("Доступна енергія", f"{available_wh:,.0f} Вт·год")
m2.metric("Запланована потреба", f"{requested_wh:,.0f} Вт·год")
m3.metric("Баланс до оптимізації", f"{available_wh-requested_wh:,.0f} Вт·год")

st.subheader("2. Оптимізація графіка")
st.markdown(
    "Модель максимізує сумарний рівень задоволення потреб з урахуванням пріоритетів. "
    "Водночас вона дотримується енергетичного бюджету, потужності інвертора та дозволених часових вікон."
)

if st.button("⚡ Розрахувати оптимальний графік", type="primary", use_container_width=True, disabled=not valid):
    n = len(edited)
    model = pulp.LpProblem("Energy_Optimizer", pulp.LpMaximize)
    x = {}
    rows = [r for _, r in edited.reset_index(drop=True).iterrows()]
    for i, r in enumerate(rows):
        start = int(r["Початок вікна"])
        end = int(r["Кінець вікна"])
        for t in range(outage_hours):
            x[i, t] = pulp.LpVariable(f"x_{i}_{t}", cat="Binary")
            if not (start <= t < end):
                model += x[i, t] == 0

    # Не можна перевищити заплановану потребу кожного приладу.
    for i, r in enumerate(rows):
        model += pulp.lpSum(x[i, t] for t in range(outage_hours)) <= int(r["Потрібно годин"])

    # Загальний запас енергії.
    model += pulp.lpSum(
        float(rows[i]["Потужність, Вт"]) * x[i, t]
        for i in range(n) for t in range(outage_hours)
    ) <= available_wh

    # Максимальна сумарна потужність у кожну годину.
    for t in range(outage_hours):
        model += pulp.lpSum(
            float(rows[i]["Потужність, Вт"]) * x[i, t] for i in range(n)
        ) <= inverter_w

    # Нормована корисність: пріоритет, поділений на потрібну кількість годин.
    objective_terms = []
    for i, r in enumerate(rows):
        need = int(r["Потрібно годин"])
        if need > 0:
            weight = float(r["Пріоритет"]) / need
            objective_terms.extend(weight * x[i, t] for t in range(outage_hours))
    model += pulp.lpSum(objective_terms)

    solver = pulp.PULP_CBC_CMD(msg=False)
    status = model.solve(solver)

    if pulp.LpStatus[status] not in ("Optimal", "Feasible"):
        st.error("Не вдалося знайти допустимий розклад. Перевірте вхідні параметри.")
    else:
        schedule = []
        summary = []
        for i, r in enumerate(rows):
            used = 0
            for t in range(outage_hours):
                active = int(round(pulp.value(x[i, t]) or 0))
                if active:
                    used += 1
                schedule.append({
                    "Година": f"{t:02d}:00–{t+1:02d}:00",
                    "Номер години": t + 1,
                    "Прилад": r["Прилад"],
                    "Потужність, Вт": float(r["Потужність, Вт"]),
                    "Працює": active,
                    "Енергія, Вт·год": float(r["Потужність, Вт"]) * active
                })
            need = int(r["Потрібно годин"])
            summary.append({
                "Прилад": r["Прилад"],
                "Потрібно годин": need,
                "Заплановано годин": used,
                "Виконання потреби, %": round(100 * used / need, 1) if need else 100.0,
                "Пріоритет": int(r["Пріоритет"]),
                "Енергія, Вт·год": float(r["Потужність, Вт"]) * used
            })

        sched_df = pd.DataFrame(schedule)
        summary_df = pd.DataFrame(summary)
        hourly = sched_df.groupby(["Номер години", "Година"], as_index=False)["Енергія, Вт·год"].sum()
        hourly["Потужність, Вт"] = hourly["Енергія, Вт·год"]
        total_used = float(hourly["Енергія, Вт·год"].sum())
        total_service = sum(s["Заплановано годин"] for s in summary)
        total_requested = sum(s["Потрібно годин"] for s in summary)
        remaining = available_wh - total_used

        st.success(f"Оптимізацію завершено. Статус розв'язку: {pulp.LpStatus[status]}.")
        a, b, c, d = st.columns(4)
        a.metric("Використано енергії", f"{total_used:,.0f} Вт·год")
        b.metric("Залишок доступної енергії", f"{remaining:,.0f} Вт·год")
        c.metric("Заплановано годин роботи", f"{total_service} год")
        d.metric("Загальна потреба", f"{total_requested} год")

        st.markdown("#### Оптимальний графік")
        pivot = sched_df.pivot(index="Прилад", columns="Номер години", values="Працює")
        pivot.columns = [f"Год. {c}" for c in pivot.columns]
        st.dataframe(pivot, use_container_width=True)

        st.markdown("#### Виконання потреб кожного приладу")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        fig1 = px.bar(summary_df, x="Прилад", y="Виконання потреби, %", color="Пріоритет",
                      range_y=[0, 105], title="Частка задоволеної потреби за приладами",
                      color_continuous_scale="Blues")
        st.plotly_chart(fig1, use_container_width=True)

        st.markdown("#### Навантаження за годинами")
        fig2 = px.bar(hourly, x="Година", y="Енергія, Вт·год",
                      title="Енергія, використана в кожному часовому інтервалі")
        fig2.add_hline(y=inverter_w, line_dash="dash", annotation_text="Ліміт потужності інвертора (Вт)")
        st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Перевірка енергетичного балансу")
        st.progress(min(1.0, total_used / available_wh) if available_wh else 0.0)
        st.write(f"Використано **{total_used:.1f} Вт·год** із доступних **{available_wh:.1f} Вт·год**.")
        st.download_button(
            "⬇️ Завантажити результати у CSV",
            data=summary_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="energy_optimizer_results.csv",
            mime="text/csv",
            use_container_width=True
        )
        st.info(
            "Інтерпретація: модель розподіляє години роботи відповідно до пріоритетів і заданих обмежень. "
            "Вона не враховує пускові струми, змінну потужність, переривання циклів холодильника та "
            "мінімальну тривалість безперервної роботи. Для таких випадків модель можна розширити."
        )

with st.expander("Математична модель, використана в програмі"):
    st.markdown(r"""
**Змінна рішення:** \(x_{it}\in\{0,1\}\) — чи працює прилад \(i\) у годину \(t\).

**Цільова функція:**
\[
\max Z=\sum_i\sum_t \frac{w_i}{h_i}x_{it},
\]
де \(w_i\) — пріоритет приладу, \(h_i\) — потрібна кількість годин його роботи.

**Обмеження енергетичного запасу:**
\[
\sum_i\sum_t P_i x_{it}\le E_{\mathrm{доступна}},
\qquad
E_{\mathrm{доступна}}=C\cdot\eta\cdot(1-r).
\]

**Обмеження потужності інвертора:**
\[
\sum_i P_i x_{it}\le P_{\max}\quad \forall t.
\]

**Обмеження потреби:**
\[
\sum_t x_{it}\le h_i\quad \forall i.
\]

Значення \(P_i\) задається у ватах, а тривалість одного інтервалу дорівнює одній годині, тому добуток \(P_i x_{it}\) чисельно відповідає Вт·год за інтервал.
""")

st.caption("Навчально-дослідницький прототип для роботи МАН. Розрахунки залежать від точності введених характеристик обладнання.")
