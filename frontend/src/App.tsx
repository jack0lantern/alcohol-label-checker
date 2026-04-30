import BatchUpload from "./components/BatchUpload";
import SingleUpload from "./components/SingleUpload";

function App() {
  return (
    <main>
      <header>
        <h1>Alcohol <i>Label</i> Checker</h1>
        <p style={{ fontFamily: 'var(--font-mono)', color: '#888', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 'var(--spacing-xl)' }}>
          Automated TTB Compliance Verification System
        </p>
      </header>
      <div className="grid-layout">
        <SingleUpload />
        <BatchUpload />
      </div>
    </main>
  );
}

export default App;
