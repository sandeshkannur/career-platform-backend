import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 24 }}>
          <h2>Something crashed</h2>
          <pre style={{ whiteSpace: "pre-wrap", color: "crimson" }}>
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <p>Open DevTools Console for full stack trace.</p>
          <p>
            <a href="/dev/reset">Reset session</a>
          </p>
        </div>
      );
    }

    return this.props.children;
  }
}
