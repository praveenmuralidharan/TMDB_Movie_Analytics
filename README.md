# Reel Insights

Exploratory analysis of about 2,500 TMDB movies: six linked CSVs, a SQLite database, four notebooks, and a small Streamlit app.

## What's in the folder

- `data/` — the six CSVs and `tmdb.db` (built by the cleaning notebook)
- `01_data_cleaning.ipynb` — inspect, drop exact duplicate rows, load SQLite
- `02_sql_analysis.ipynb` — the 10 SQL questions
- `03_pandas_analysis.ipynb` — the 10 Pandas questions
- `04_visualizations.ipynb` — univariate, bivariate and multivariate charts
- `app.py` — Filters, Dashboard, Query Explorer

SQLite is used so the project runs from the files in this folder. No MySQL setup.

## How to run

From this folder:

```bash
pip install -r requirements.txt
```

Open the notebooks in order, starting with `01_data_cleaning.ipynb`, if you want to rebuild `data/tmdb.db`. The database file is already included.

```bash
streamlit run app.py
```

The sidebar filters (genre, year, minimum rating, language) are stored in session state and apply on the Dashboard and on the movie-level saved queries. Actor, director and keyword queries use the full database, and the Query Explorer page says so.

Budget and revenue of 0 are kept in the database. TMDB uses 0 when the figure is unknown. Profit, ROI and the money charts ignore those rows.

## Top 5 takeaways

1. Adventure is the strongest commercial genre in this file once zeros are dropped: average revenue is about $401 million. Avatar is the highest gross, about $2.92 billion, and most of the top 10 are adventure / action / science fiction. Titanic is the main exception.

2. 133 movies have a 0 budget or a 0 revenue. I treated that as "not reported," not as a real zero. Putting those into an average makes films look free. A few non-zero revenues are still hard to trust (The Gray Man, Red Notice), because streaming titles don't have a normal box office figure in this data.

3. Budget moves with revenue (correlation about 0.68) and does not move with rating (about -0.12). War has the highest average rating among genres with at least 20 movies, 7.36. Action makes more money and scores lower. Genre is a better clue for revenue than for whether people liked the film.

4. The wild ROI numbers are small films that blew up: Dragon Ball Super: Broly, Snow White, Rocky Horror, Rocky, all over 100x, and only after I required a budget of at least $1 million. The median ROI, on the 2,370 films with both figures, is about 2.4x. That's the number I would actually use. About 92% of those films show a reported profit, which is high and fits a file full of already-famous movies.

5. The extract is not "all movies." After dropping 6 duplicate rows there are 2,503 films, about 94% of them English, ratings clustered around 6.9, and 2016 is the busiest year in the file (121 movies) because the file is recent-heavy. Samuel L. Jackson appears most often (39 films, average rating about 6.94, close to the overall average). Steven Spielberg has the most directing credits (27).

If I were using this for a greenlight or a licensing look, I would drop the zero money fields first, compare genres on revenue, and not treat rating, keyword count, or "appeared in the most movies" as the same question. For casting, the movie count needs the average rating next to it. Tom Hanks is in fewer films than Jackson here and the average rating on those films is higher (about 7.29).
