const connectors = ["Gmail", "Google Drive", "Calendar", "MCP server"];

export default function ConnectorsPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Connectors</p>
          <h1 className="page-title">MCP and Composio-style tools</h1>
          <p className="page-subtitle">
            Manage user-connected services and the permissions Adele Web can use during tasks.
          </p>
        </div>
      </header>
      <section className="grid two">
        {connectors.map((connector) => (
          <article className="card" key={connector}>
            <h2>{connector}</h2>
            <p>Connector configuration, scopes, health, and audit records.</p>
          </article>
        ))}
      </section>
    </>
  );
}
