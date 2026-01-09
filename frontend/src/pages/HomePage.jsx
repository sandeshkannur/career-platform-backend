import { Link } from "react-router-dom";
import Page from "../ui/Page";
import Card from "../ui/Card";
import PublicHeader from "../ui/PublicHeader";

export default function HomePage() {
  return (
    <Page>
      <PublicHeader />
      <Card>
        <h1>Home</h1>
        <p>Public landing page</p>

        <div style={{ marginTop: 16 }}>
          <p>
            <Link to="/pricing">View Pricing</Link>
          </p>
        </div>
      </Card>
    </Page>
  );
}
