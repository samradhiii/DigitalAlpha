import { useEffect, useState } from "react";

// Loads data from an API call and reloads whenever `version` changes.
export default function useApiData(load, version) {
  const [state, setState] = useState({ data: null, error: "", loading: true });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    load()
      .then((data) => !cancelled && setState({ data, error: "", loading: false }))
      .catch((err) => !cancelled && setState({ data: null, error: err.message, loading: false }));
    return () => {
      cancelled = true;
    };
  }, [load, version]);

  return state;
}
