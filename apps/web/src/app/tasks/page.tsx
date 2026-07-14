const steps = ["Plan", "Read browser tab", "Compare memory", "Draft answers", "Request approval"];

export default function TasksPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Tasks</p>
          <h1 className="page-title">Planning and action timeline</h1>
          <p className="page-subtitle">
            Track task runs, steps, tool calls, outputs, failures, approvals, and final results.
          </p>
        </div>
      </header>
      <section className="card">
        <h2>Application assistant run</h2>
        <ul>
          {steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ul>
      </section>
    </>
  );
}
