// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";
import { afterAll, afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import AzureDevOpsCredentialCard from "./AzureDevOpsCredentialCard";
import * as syncServiceClient from "../services/syncServiceClient";

vi.mock("../services/syncServiceClient", () => ({
  fetchAzureDevOpsCredentialStatus: vi.fn(),
  saveAzureDevOpsCredential: vi.fn(),
  deleteAzureDevOpsCredential: vi.fn(),
}));

function renderCredentialCard() {
  return render(
    <Theme theme={neutralTheme}>
      <AzureDevOpsCredentialCard />
    </Theme>
  );
}

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute("open");
  };
  HTMLCanvasElement.prototype.getContext = vi.fn();
  window.scrollTo = vi.fn();
});

afterAll(() => {
  delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal;
  delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).close;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.mocked(syncServiceClient.fetchAzureDevOpsCredentialStatus).mockReset();
  vi.mocked(syncServiceClient.saveAzureDevOpsCredential).mockReset();
  vi.mocked(syncServiceClient.deleteAzureDevOpsCredential).mockReset();
});

describe("AzureDevOpsCredentialCard", () => {
  test("loads Azure DevOps credential status", async () => {
    vi.mocked(syncServiceClient.fetchAzureDevOpsCredentialStatus).mockResolvedValue({
      configured: true,
      updated_at: "2026-08-18T12:00:00",
    });

    renderCredentialCard();

    expect(await screen.findByText("Configured")).toBeInTheDocument();
    expect(syncServiceClient.fetchAzureDevOpsCredentialStatus).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Updated at 2026-08-18T12:00:00")).toBeInTheDocument();
  });

  test("saves a PAT, clears the password field, and shows configured status", async () => {
    vi.mocked(syncServiceClient.fetchAzureDevOpsCredentialStatus).mockResolvedValue({
      configured: false,
      updated_at: null,
    });
    vi.mocked(syncServiceClient.saveAzureDevOpsCredential).mockResolvedValue({
      configured: true,
      updated_at: "2026-08-18T12:00:00",
    });

    renderCredentialCard();

    fireEvent.change(await screen.findByLabelText(/^Azure DevOps personal access token/), {
      target: { value: "browser-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save credential" }));

    await waitFor(() => {
      expect(syncServiceClient.saveAzureDevOpsCredential).toHaveBeenCalledWith("browser-secret");
    });
    expect(screen.getByLabelText(/^Azure DevOps personal access token/)).toHaveValue("");
    expect(screen.getByText("Configured")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("browser-secret")).not.toBeInTheDocument();
  });

  test("disables save when the PAT exceeds 4096 characters", async () => {
    vi.mocked(syncServiceClient.fetchAzureDevOpsCredentialStatus).mockResolvedValue({
      configured: false,
      updated_at: null,
    });

    renderCredentialCard();

    fireEvent.change(await screen.findByLabelText(/^Azure DevOps personal access token/), {
      target: { value: "x".repeat(4097) },
    });

    expect(screen.getByRole("button", { name: "Save credential" })).toBeDisabled();
  });

  test("shows a save failure in an Astryx banner", async () => {
    vi.mocked(syncServiceClient.fetchAzureDevOpsCredentialStatus).mockResolvedValue({
      configured: false,
      updated_at: null,
    });
    vi.mocked(syncServiceClient.saveAzureDevOpsCredential).mockRejectedValue(
      new Error("Sync service request failed: 500: credential could not be stored")
    );

    renderCredentialCard();

    fireEvent.change(await screen.findByLabelText(/^Azure DevOps personal access token/), {
      target: { value: "browser-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save credential" }));

    expect(await screen.findByText("Unable to save credential")).toBeInTheDocument();
    expect(screen.getByText("Sync service request failed: 500: credential could not be stored")).toBeInTheDocument();
  });

  test("confirms removal before deleting the credential", async () => {
    vi.mocked(syncServiceClient.fetchAzureDevOpsCredentialStatus).mockResolvedValue({
      configured: true,
      updated_at: "2026-08-18T12:00:00",
    });
    vi.mocked(syncServiceClient.deleteAzureDevOpsCredential).mockResolvedValue(undefined);

    renderCredentialCard();

    fireEvent.click(await screen.findByRole("button", { name: "Remove credential" }));

    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("Remove Azure DevOps credential?");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove credential" }));

    await waitFor(() => {
      expect(syncServiceClient.deleteAzureDevOpsCredential).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText("Not configured")).toBeInTheDocument();
  });
});
