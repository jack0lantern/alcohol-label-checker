import BatchUpload from "./components/BatchUpload";
import SingleUpload from "./components/SingleUpload";

function App() {
  return (
    <main>
      <h1>Alcohol Label Checker</h1>
      <SingleUpload />
      <BatchUpload />
    </main>
  );
}

export default App;
