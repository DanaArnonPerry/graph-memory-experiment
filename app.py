def draw_bar_chart(sub: pd.DataFrame, title: str | None = None, height: int = 380):
    if sub.empty:
        st.warning("לא נמצאו נתונים לגרף בקובץ graph_DB.csv")
        return

    BAR_SIZE = 20  # רוחב עמודה קבוע (פיקסלים) – ~40% מהרוחב הרגיל

    def _pick(col_main: str, col_alt: str, default: str):
        if col_main in sub.columns and sub[col_main].notna().any():
            return str(sub[col_main].dropna().iloc[0])
        if col_alt in sub.columns and sub[col_alt].notna().any():
            return str(sub[col_alt].dropna().iloc[0])
        return default

    name_a = _pick('SeriesAName', 'SeriesnameA', 'סדרה A')
    name_b = _pick('SeriesBName', 'SeriesnameB', 'סדרה B')

    col_a = (sub['ColorA'].dropna().iloc[0]
             if 'ColorA' in sub.columns and sub['ColorA'].notna().any() else '#4C78A8')
    col_b = (sub['ColorB'].dropna().iloc[0]
             if 'ColorB' in sub.columns and sub['ColorB'].notna().any() else '#F58518')

    has_b = 'ValuesB' in sub.columns and sub['ValuesB'].notna().any()

    # Altair
    if _HAS_ALT:
        x_axis = alt.Axis(labelAngle=0, labelPadding=6, title=None,
                          labelFontSize=14, labelColor='#000')
        y_axis = alt.Axis(grid=True, tickCount=6, title=None)

        if has_b:
            df_long = sub[['Labels','ValuesA','ValuesB']].copy()
            df_long = df_long.melt(id_vars=['Labels'], value_vars=['ValuesA','ValuesB'],
                                   var_name='series', value_name='value')
            df_long['series_name'] = df_long['series'].map({'ValuesA': name_a, 'ValuesB': name_b})

            base = alt.Chart(df_long).encode(
                x=alt.X('Labels:N', sort=None, axis=x_axis),   # <- הסרנו scale=alt.Scale(band=...)
                y=alt.Y('value:Q', axis=y_axis),
                color=alt.Color('series_name:N',
                                scale=alt.Scale(domain=[name_a, name_b], range=[col_a, col_b]),
                                legend=alt.Legend(orient='top-right', title=None)),
                xOffset='series_name:N',
                tooltip=['Labels','series_name', alt.Tooltip('value:Q', format='.0f')]
            )
            bars = base.mark_bar(size=BAR_SIZE)
            labels = base.mark_text(color='black', dy=-6).encode(text=alt.Text('value:Q', format='.0f'))
            chart = bars + labels
        else:
            base = alt.Chart(sub[['Labels','ValuesA']]).encode(
                x=alt.X('Labels:N', sort=None, axis=x_axis),     # <- ללא scale=...
                y=alt.Y('ValuesA:Q', axis=y_axis),
                tooltip=['Labels', alt.Tooltip('ValuesA:Q', format='.0f')]
            )
            bars = base.mark_bar(color=col_a, size=BAR_SIZE)
            labels = alt.Chart(sub[['Labels','ValuesA']]).mark_text(color='black', dy=-6).encode(
                x='Labels:N', y='ValuesA:Q', text=alt.Text('ValuesA:Q', format='.0f')
            )
            chart = bars + labels

        chart = chart.properties(height=height, padding={"top": 36, "left": 10, "right": 10, "bottom": 6})
        st.altair_chart(chart, use_container_width=True)
        return

    # Matplotlib (גיבוי)
    if _HAS_MPL:
        labels = sub['Labels'].astype(str).tolist() if 'Labels' in sub.columns else [str(i) for i in range(len(sub))]
        vals_a = sub['ValuesA'].fillna(0).tolist() if 'ValuesA' in sub.columns else [0]*len(labels)
        x = range(len(labels))
        if has_b:
            vals_b = sub['ValuesB'].fillna(0).tolist()
            width = 0.18
        else:
            vals_b = None
            width = 0.25
        fig, ax = plt.subplots(figsize=(min(14, max(8, len(labels)*0.8)), height/96))
        if has_b:
            ax.bar([i - width/2 for i in x], vals_a, width, label=name_a, color=col_a)
            ax.bar([i + width/2 for i in x], vals_b, width, label=name_b, color=col_b)
            ax.legend(loc='upper right', frameon=False)
        else:
            ax.bar(x, vals_a, width, color=col_a)
        ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=0, ha='center', fontsize=14, color='black')
        ax.set_xlabel(''); ax.set_ylabel('')
        ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.25)
        fig.subplots_adjust(top=0.90)
        def _annot(xs, ys):
            for xi, yi in zip(xs, ys):
                ax.text(xi, yi, f"{yi:.0f}", ha='center', va='bottom', fontsize=12, color='black')
        if has_b:
            _annot([i - width/2 for i in x], vals_a); _annot([i + width/2 for i in x], vals_b)
        else:
            _annot(list(x), vals_a)
        st.pyplot(fig, clear_figure=True)
        return

    # st.bar_chart (גיבוי אחרון)
    if has_b:
        data = sub[['Labels','ValuesA','ValuesB']].copy()
        data.rename(columns={'ValuesA': name_a, 'ValuesB': name_b}, inplace=True)
    else:
        data = sub[['Labels','ValuesA']].copy()
        data.rename(columns={'ValuesA': name_a}, inplace=True)
    st.bar_chart(data.set_index('Labels'))
