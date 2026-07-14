const entries = [
  "Profile summary",
  "Preferred job locations",
  "Resume highlights",
  "Application tone",
];

export default function MemoryPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Memory</p>
          <h1 className="page-title">Cloud memory vault</h1>
          <p className="page-subtitle">
            Review, edit, approve, delete, and reset the memories Adele Web can use.
          </p>
        </div>
      </header>
      <section className="grid two">
        {entries.map((entry) => (
          <article className="card" key={entry}>
            <h2>{entry}</h2>
            <p>Reviewed memory entry with provenance, category, and retention controls.</p>
          </article>
        ))}
      </section>
    </>
  );
}
