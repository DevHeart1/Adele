const settings = [
  "Memory retention",
  "Browser automation permissions",
  "Connector permissions",
  "Audit log redaction",
];

export default function SettingsPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Settings</p>
          <h1 className="page-title">Privacy and control</h1>
          <p className="page-subtitle">
            Configure what Adele Web can remember, automate, connect to, and retain.
          </p>
        </div>
      </header>
      <section className="grid two">
        {settings.map((setting) => (
          <article className="card" key={setting}>
            <h2>{setting}</h2>
            <p>User-visible controls for B0 privacy and approval boundaries.</p>
          </article>
        ))}
      </section>
    </>
  );
}
