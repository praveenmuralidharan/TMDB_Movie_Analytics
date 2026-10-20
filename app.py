# Reel Insights
# Run 01_data_cleaning.ipynb first so data/tmdb.db exists, then:
#   streamlit run app.py

import os
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Reel Insights", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "tmdb.db")


@st.cache_data
def load_tables():
    con = sqlite3.connect(DB_PATH)
    movies = pd.read_sql("SELECT * FROM movies", con)
    genres = pd.read_sql("SELECT * FROM genres", con)
    movie_genres = pd.read_sql(
        "SELECT rowid AS genre_row, movie_id, genre_id FROM movie_genres ORDER BY rowid",
        con,
    )
    cast = pd.read_sql("SELECT movie_id, person_id FROM cast", con)
    con.close()
    movies["year"] = movies["release_date"].str.slice(0, 4).astype(int)
    return movies, genres, movie_genres, cast


def money(value):
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f} billion"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.0f} million"
    return f"${value:,.0f}"


def filtered_movies(movies, movie_genres, genres):
    # widget keys live in session_state, so the same filters hit every page
    df = movies.copy()
    year_from, year_to = st.session_state.year_range
    df = df[(df["year"] >= year_from) & (df["year"] <= year_to)]
    df = df[df["vote_average"] >= st.session_state.min_rating]
    if st.session_state.language != "All":
        df = df[df["original_language"] == st.session_state.language]
    picked = st.session_state.selected_genres
    if picked:
        ids = movie_genres.merge(genres, on="genre_id")
        ids = ids.loc[ids["genre_name"].isin(picked), "movie_id"]
        df = df[df["movie_id"].isin(ids)]
    return df


def movie_where():
    """SQL conditions on alias m, matching the sidebar."""
    parts = ["1=1"]
    params = []
    picked = st.session_state.selected_genres
    if picked:
        marks = ",".join("?" for _ in picked)
        parts.append(
            f"""m.movie_id IN (
                SELECT mg.movie_id
                FROM movie_genres mg
                JOIN genres g ON g.genre_id = mg.genre_id
                WHERE g.genre_name IN ({marks})
            )"""
        )
        params.extend(list(picked))
    year_from, year_to = st.session_state.year_range
    parts.append("CAST(strftime('%Y', m.release_date) AS INTEGER) BETWEEN ? AND ?")
    params.extend([int(year_from), int(year_to)])
    parts.append("m.vote_average >= ?")
    params.append(float(st.session_state.min_rating))
    if st.session_state.language != "All":
        parts.append("m.original_language = ?")
        params.append(st.session_state.language)
    return " AND ".join(parts), params


def run_sql(sql, params):
    con = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


# Questions 4, 5, 6 and 8 are about people or keywords, not a movie slice,
# so the sidebar is not applied to those.
QUERIES = [
    {
        "label": "1. Action movies after 2015",
        "use_filters": True,
        "sql": """
            SELECT m.title, m.release_date
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON g.genre_id = mg.genre_id
            WHERE g.genre_name = 'Action'
              AND m.release_date > '2015-12-31'
              AND {where}
            ORDER BY m.release_date
        """,
    },
    {
        "label": "2. Top 10 highest-grossing movies",
        "use_filters": True,
        "sql": """
            SELECT m.title, m.revenue, GROUP_CONCAT(g.genre_name, ', ') AS genres
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON g.genre_id = mg.genre_id
            WHERE {where}
            GROUP BY m.movie_id
            ORDER BY m.revenue DESC
            LIMIT 10
        """,
    },
    {
        "label": "3. Average budget and revenue by genre",
        "use_filters": True,
        "sql": """
            SELECT g.genre_name,
                   ROUND(AVG(m.budget)) AS avg_budget,
                   ROUND(AVG(m.revenue)) AS avg_revenue,
                   COUNT(*) AS n_movies
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON g.genre_id = mg.genre_id
            WHERE m.budget > 0 AND m.revenue > 0
              AND {where}
            GROUP BY g.genre_name
            ORDER BY avg_revenue DESC
        """,
    },
    {
        "label": "4. Top 10 actors by movie count",
        "use_filters": False,
        "sql": """
            SELECT actor_name, COUNT(DISTINCT movie_id) AS movie_count
            FROM cast
            GROUP BY person_id, actor_name
            ORDER BY movie_count DESC
            LIMIT 10
        """,
    },
    {
        "label": "5. Directors with more than 3 movies",
        "use_filters": False,
        "sql": """
            SELECT person_name, COUNT(DISTINCT movie_id) AS movie_count
            FROM crew
            WHERE job = 'Director'
            GROUP BY person_id, person_name
            HAVING movie_count > 3
            ORDER BY movie_count DESC
        """,
    },
    {
        "label": "6. Top 10 keywords",
        "use_filters": False,
        "sql": """
            SELECT keyword_name, COUNT(*) AS times_used
            FROM movie_keywords
            GROUP BY keyword_id, keyword_name
            ORDER BY times_used DESC
            LIMIT 10
        """,
    },
    {
        "label": "7. Above-average budget, below-average revenue",
        "use_filters": True,
        "sql": """
            SELECT m.title, m.budget, m.revenue
            FROM movies m
            WHERE m.budget > (SELECT AVG(budget) FROM movies WHERE budget > 0)
              AND m.revenue < (SELECT AVG(revenue) FROM movies WHERE revenue > 0)
              AND m.budget > 0 AND m.revenue > 0
              AND {where}
            ORDER BY m.budget DESC
        """,
    },
    {
        "label": "8. Actors in a Christopher Nolan film",
        "use_filters": False,
        "sql": """
            SELECT DISTINCT c.actor_name
            FROM cast c
            JOIN crew cr ON c.movie_id = cr.movie_id
            WHERE cr.person_name = 'Christopher Nolan'
              AND cr.job = 'Director'
            ORDER BY c.actor_name
        """,
    },
    {
        "label": "9. Highest rated genres (at least 20 movies)",
        "use_filters": True,
        "sql": """
            SELECT g.genre_name,
                   ROUND(AVG(m.vote_average), 2) AS avg_rating,
                   COUNT(DISTINCT m.movie_id) AS n_movies
            FROM movies m
            JOIN movie_genres mg ON m.movie_id = mg.movie_id
            JOIN genres g ON g.genre_id = mg.genre_id
            WHERE {where}
            GROUP BY g.genre_name
            HAVING n_movies >= 20
            ORDER BY avg_rating DESC
        """,
    },
    {
        "label": "10. Top 10 movies by keyword count",
        "use_filters": True,
        "sql": """
            SELECT m.title, COUNT(k.keyword_id) AS keyword_count
            FROM movies m
            JOIN movie_keywords k ON m.movie_id = k.movie_id
            WHERE {where}
            GROUP BY m.movie_id
            ORDER BY keyword_count DESC
            LIMIT 10
        """,
    },
]


def query_insight(label, df):
    if df.empty:
        return "Nothing matched. The filters may be cutting this question down to zero rows."
    row = df.iloc[0]
    if label.startswith("1."):
        return (
            f"{len(df)} action movies after 2015 match. "
            f"Earliest in this cut is {row.title} ({row.release_date})."
        )
    if label.startswith("2."):
        return f"{row.title} is the top grosser here, at {money(row.revenue)}."
    if label.startswith("3."):
        return (
            f"{row.genre_name} has the highest average revenue in this cut, "
            f"about {money(row.avg_revenue)} across {int(row.n_movies)} movies. "
            "Zeros were left out of the average."
        )
    if label.startswith("4."):
        return f"{row.actor_name} is in the most movies ({int(row.movie_count)})."
    if label.startswith("5."):
        return (
            f"{len(df)} directors have more than 3 films. "
            f"{row.person_name} has the most, with {int(row.movie_count)}."
        )
    if label.startswith("6."):
        return f"Most common keyword is \"{row.keyword_name}\" ({int(row.times_used)} movies)."
    if label.startswith("7."):
        return (
            f"{len(df)} movies spent more than the overall average budget and "
            f"made less than the overall average revenue. "
            f"The most expensive of them here is {row.title}."
        )
    if label.startswith("8."):
        return f"{len(df)} actors appear in a film Christopher Nolan directed."
    if label.startswith("9."):
        return (
            f"{row.genre_name} has the highest average rating "
            f"({row.avg_rating}) among genres with at least 20 movies in this cut."
        )
    if label.startswith("10."):
        return f"{row.title} has the most keywords tagged ({int(row.keyword_count)})."
    return ""


def draw_chart(label, df):
    if df.empty:
        return
    if label.startswith("1."):
        counts = (
            df.assign(year=df["release_date"].astype(str).str.slice(0, 4))
            .groupby("year")
            .size()
            .reset_index(name="movies")
        )
        fig = px.bar(counts, x="year", y="movies", title="Action movies per year")
        st.plotly_chart(fig, width="stretch")
    elif label.startswith("2."):
        fig = px.bar(df, x="revenue", y="title", orientation="h", title="Top 10 by revenue")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
    elif label.startswith("3."):
        fig = px.bar(df, x="avg_revenue", y="genre_name", orientation="h", title="Average revenue by genre")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
    elif label.startswith("4."):
        fig = px.bar(df, x="movie_count", y="actor_name", orientation="h", title="Movies per actor")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
    elif label.startswith("5."):
        top = df.head(15)
        fig = px.bar(top, x="movie_count", y="person_name", orientation="h", title="Directors with the most films")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.caption("Chart is the top 15. The table is everyone over 3 films.")
        st.plotly_chart(fig, width="stretch")
    elif label.startswith("6."):
        fig = px.bar(df, x="times_used", y="keyword_name", orientation="h", title="Most used keywords")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
    elif label.startswith("7."):
        gap = df.copy()
        gap["shortfall"] = gap["budget"] - gap["revenue"]
        gap = gap.nlargest(10, "shortfall")
        fig = px.bar(gap, x="shortfall", y="title", orientation="h", title="Largest budget minus revenue")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.caption("Chart is the 10 biggest gaps. The table is the full list. Averages in the query are for the whole database.")
        st.plotly_chart(fig, width="stretch")
    elif label.startswith("8."):
        st.caption("This is a list of names, so I didn't add a chart.")
    elif label.startswith("9."):
        fig = px.bar(df, x="avg_rating", y="genre_name", orientation="h", title="Average rating by genre")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis={"range": [6, 8]})
        st.plotly_chart(fig, width="stretch")
    elif label.startswith("10."):
        fig = px.bar(df, x="keyword_count", y="title", orientation="h", title="Keyword count")
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")


def dashboard_sentence(picked, movie_genres, genres):
    if picked.empty:
        return "No movies match these filters."
    top = picked.sort_values("revenue", ascending=False).iloc[0]
    first_genre = movie_genres.sort_values("genre_row").drop_duplicates("movie_id")
    joined = picked.merge(first_genre, on="movie_id", how="left").merge(genres, on="genre_id", how="left")
    with_money = joined[joined["revenue"] > 0]
    sentence = f"Highest grossing title in this selection is {top.title} ({money(top.revenue)})."
    if not with_money.empty and with_money["genre_name"].notna().any():
        totals = with_money.groupby("genre_name")["revenue"].sum().sort_values(ascending=False)
        sentence += (
            f" Using each movie's first listed genre, {totals.index[0]} "
            f"accounts for the most revenue ({money(totals.iloc[0])})."
        )
    return sentence


def filters_page():
    st.header("Filters")
    st.write(
        f"{len(picked):,} movies match the sidebar. "
        "Leave genre empty if you want every genre. Language starts on All."
    )
    st.write(
        "Budget and revenue of 0 are still in this list. TMDB uses 0 when the number wasn't reported. "
        "The dashboard scatter drops those rows."
    )
    show = picked.sort_values("revenue", ascending=False)[
        ["title", "year", "original_language", "vote_average", "budget", "revenue"]
    ].head(25)
    st.caption("First 25 matching movies, by revenue.")
    st.dataframe(show, width="stretch", hide_index=True)


def dashboard_page():
    st.header("Dashboard")
    st.write(f"{len(picked):,} movies match the sidebar.")

    genre_links = movie_genres.merge(genres, on="genre_id")
    genre_links = genre_links[genre_links["movie_id"].isin(picked["movie_id"])]
    n_genres = int(genre_links["genre_id"].nunique()) if not picked.empty else 0
    n_actors = int(cast.loc[cast["movie_id"].isin(picked["movie_id"]), "person_id"].nunique()) if not picked.empty else 0
    avg_rating = float(picked["vote_average"].mean()) if not picked.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Movies", f"{len(picked):,}")
    c2.metric("Genres", f"{n_genres:,}")
    c3.metric("Actors", f"{n_actors:,}")
    c4.metric("Average rating", f"{avg_rating:.2f}")

    st.info(dashboard_sentence(picked, movie_genres, genres))

    left, right = st.columns(2)
    with left:
        top = picked.nlargest(10, "revenue")
        if top.empty or top["revenue"].sum() == 0:
            st.write("No reported revenue in this selection.")
        else:
            fig = px.bar(top, x="revenue", y="title", orientation="h", title="Top 10 by revenue")
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, width="stretch")
    with right:
        if genre_links.empty:
            st.write("No genres in this selection.")
        else:
            counts = genre_links["genre_name"].value_counts().reset_index()
            counts.columns = ["genre", "movies"]
            fig = px.pie(counts, names="genre", values="movies", hole=0.45, title="Genre mix")
            st.plotly_chart(fig, width="stretch")
            st.caption("A movie in two genres is counted in both slices.")

    money_rows = picked[(picked["budget"] > 0) & (picked["revenue"] > 0)]
    st.write(f"Budget vs revenue ({len(money_rows):,} movies with both figures above 0).")
    if money_rows.empty:
        st.write("Nothing to plot. Every matching movie is missing a budget or a revenue.")
    else:
        fig = px.scatter(
            money_rows,
            x="budget",
            y="revenue",
            hover_name="title",
            title="Budget vs revenue",
        )
        st.plotly_chart(fig, width="stretch")


def explorer_page():
    st.header("Query Explorer")
    st.write(f"{len(picked):,} movies match the sidebar.")
    labels = [q["label"] for q in QUERIES]
    choice = st.selectbox("Saved query", labels)
    query = next(q for q in QUERIES if q["label"] == choice)

    if query["use_filters"]:
        where, params = movie_where()
        sql = query["sql"].format(where=where)
        st.caption("Sidebar filters are applied on top of this query.")
    else:
        sql = query["sql"]
        params = []
        st.caption("This question isn't a movie filter, so the sidebar is not applied. It uses the full database.")

    if choice.startswith("7."):
        st.caption("The average budget and average revenue inside the query stay global. Filters only change which movies are listed.")

    df = run_sql(sql, params)
    st.dataframe(df, width="stretch", hide_index=True)
    draw_chart(choice, df)
    st.info(query_insight(choice, df))
    with st.expander("SQL"):
        st.code(sql.strip(), language="sql")


if not os.path.exists(DB_PATH):
    st.error("data/tmdb.db is missing. Run 01_data_cleaning.ipynb from the project folder first.")
    st.stop()

movies, genres, movie_genres, cast = load_tables()

st.sidebar.header("Filters")
st.sidebar.caption("Saved in session state, so they stick when you change page.")
st.sidebar.multiselect(
    "Genre",
    options=sorted(genres["genre_name"].unique()),
    placeholder="All genres",
    key="selected_genres",
)
year_min = int(movies["year"].min())
year_max = int(movies["year"].max())
st.sidebar.slider("Release year", year_min, year_max, (year_min, year_max), key="year_range")
st.sidebar.slider("Minimum rating", 0.0, 10.0, 0.0, 0.1, key="min_rating")
st.sidebar.selectbox(
    "Language",
    options=["All"] + sorted(movies["original_language"].unique()),
    key="language",
)

picked = filtered_movies(movies, movie_genres, genres)
st.sidebar.metric("Movies matching", f"{len(picked):,}")

nav = st.navigation(
    [
        st.Page(filters_page, title="Filters", default=True),
        st.Page(dashboard_page, title="Dashboard", url_path="dashboard"),
        st.Page(explorer_page, title="Query Explorer", url_path="query-explorer"),
    ]
)
nav.run()
