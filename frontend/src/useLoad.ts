import { useEffect, useState } from "react";
import { ApiError } from "./api";

export type Load<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "ready"; data: T };

export function toApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError("server", "Unexpected error.");
}

/** Run `fetcher` whenever `key` changes. A response for an old key is dropped. */
export function useLoad<T>(key: string | null, fetcher: () => Promise<T>) {
  const [state, setState] = useState<Load<T>>({ status: "loading" });

  useEffect(() => {
    if (key === null) return;
    let current = true;
    setState({ status: "loading" });
    fetcher().then(
      (data) => current && setState({ status: "ready", data }),
      (err) => current && setState({ status: "error", error: toApiError(err) }),
    );
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` stands for the fetcher's inputs
  }, [key]);

  return [state, setState] as const;
}
