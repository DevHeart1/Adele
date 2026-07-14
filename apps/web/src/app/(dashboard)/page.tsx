import { z } from "zod";

const taskSchema = z.object({
  label: z.string(),
  value: z.string(),
});

const taskStats = [
  { label: "Queued approvals", value: "3" },
  { label: "Memory entries", value: "128" },
  { label: "Connected tools", value: "4" },
].map((item) => taskSchema.parse(item));

export default function DashboardPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1 className="page-title">Command Adele across browser and cloud tasks.</h1>
          <p className="page-subtitle">
            This scaffold anchors the B0 product contract: chat, cloud memory,
            browser automation, approvals, connector management, audit logs, and settings.
          </p>
        </div>
        <span className="status-pill">B1 scaffold</span>
      </header>

      <section className="command-panel" aria-label="Command Adele">
        <textarea
          className="command-input"
          defaultValue="Review the active job listing, compare it with my profile, and prepare safe application answers."
        />
        <div className="button-row">
          <span className="button secondary">Save draft</span>
          <span className="button primary">Plan task</span>
        </div>
      </section>

      <section className="grid three" style={{ marginTop: 16 }}>
        {taskStats.map((item) => (
          <article className="card" key={item.label}>
            <h2>{item.value}</h2>
            <p>{item.label}</p>
          </article>
        ))}
      </section>

      <section className="grid two" style={{ marginTop: 16 }}>
        <article className="card">
          <h2>Job application workflow</h2>
          <ul>
            <li>Read active browser tab through the extension.</li>
            <li>Compare listing requirements with memory vault profile.</li>
            <li>Draft answers and pause before submission.</li>
          </ul>
        </article>
        <article className="card">
          <h2>Runtime boundary</h2>
          <p>
            Adele Web owns browser and cloud automation. Adele Desktop remains the local
            computer assistant for native apps and files.
          </p>
        </article>
      </section>
    </>
  );
}
