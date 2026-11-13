// Result count, the list itself, and the "Show more" button. Shared by both tabs.
export default function Feed({ feed, noun, gridClass, emptyText, render }) {
  const { items, total, loading, error, hasMore, loadMore, retry } = feed;

  if (error && items.length === 0) {
    return (
      <div className="notice">
        <p>The {noun}s could not load: {error}.</p>
        <button type="button" className="primary" onClick={retry}>Try again</button>
      </div>
    );
  }

  return (
    <>
      <p className="result-count">
        {total === null ? `Loading ${noun}s` : `${total.toLocaleString()} ${noun}${total === 1 ? "" : "s"}`}
      </p>
      {total === 0 && <div className="notice"><p>{emptyText}</p></div>}
      <div className={gridClass} aria-busy={loading}>
        {items.map(render)}
      </div>
      {hasMore && (
        <div className="more">
          <button type="button" onClick={loadMore} disabled={loading}>
            {loading ? "Loading" : `Show more (${(total - items.length).toLocaleString()} left)`}
          </button>
        </div>
      )}
      {error && items.length > 0 && <p className="hint">Could not load more: {error}</p>}
    </>
  );
}
