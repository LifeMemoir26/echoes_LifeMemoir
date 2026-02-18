import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoirReaderPage } from "@/components/memoir/memoir-reader-page";

const mutateAsync = vi.fn(async () => undefined);

vi.mock("@/lib/hooks/use-generate-memoir", () => ({
  useGenerateMemoir: () => ({
    mutateAsync,
    data: null,
    normalizedError: null,
    isPending: false,
    canRetry: false
  })
}));

describe("MemoirReaderPage", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    mutateAsync.mockImplementation(async () => undefined);
  });

  it("renders base state", () => {
    render(<MemoirReaderPage />);
    expect(screen.getByRole("heading", { name: "回忆录阅读" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /生成回忆录/ })).toBeInTheDocument();
  });

  it("submits only through explicit action", async () => {
    const user = userEvent.setup();
    render(<MemoirReaderPage />);

    await user.type(screen.getByLabelText("用户名"), "alice");
    await user.click(screen.getByRole("button", { name: /生成回忆录/ }));

    expect(mutateAsync).toHaveBeenCalledTimes(1);
  });

  it("prevents duplicate submit on double click", async () => {
    const user = userEvent.setup();
    let resolveRequest: ((value: undefined) => void) | undefined;
    mutateAsync.mockImplementationOnce(
      () =>
        new Promise<undefined>((resolve) => {
          resolveRequest = resolve;
        })
    );

    render(<MemoirReaderPage />);
    await user.type(screen.getByLabelText("用户名"), "alice");
    await user.dblClick(screen.getByRole("button", { name: /生成回忆录/ }));

    expect(mutateAsync).toHaveBeenCalledTimes(1);
    resolveRequest?.(undefined);
  });
});
