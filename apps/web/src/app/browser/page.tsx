export default function BrowserPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Browser</p>
          <h1 className="page-title">Extension automation bridge</h1>
          <p className="page-subtitle">
            Inspect active-tab snapshots, element refs, queued actions, and browser action results.
          </p>
        </div>
        <span className="status-pill">Extension pending</span>
      </header>
      <section className="grid two">
        <article className="card">
          <h2>Snapshot contract</h2>
          <p>URL, title, viewport, element refs, text regions, and timestamp.</p>
        </article>
        <article className="card">
          <h2>Action contract</h2>
          <p>Read, find, click, type, select, scroll, extract, and report result.</p>
        </article>
      </section>
    </>
  );
}
