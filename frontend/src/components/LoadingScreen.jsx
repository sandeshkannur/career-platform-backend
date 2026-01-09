// src/components/LoadingScreen.jsx
import Page from "../ui/Page";
import Card from "../ui/Card";

export default function LoadingScreen({ label = "Loading…" }) {
  return (
    <Page>
      <Card>
        <h2 style={{ margin: 0 }}>{label}</h2>
      </Card>
    </Page>
  );
}
