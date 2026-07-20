import { useCallback, useEffect, useRef, useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Card, HStack, VStack } from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import {
  createSyncAreaPath,
  deleteSyncAreaPath,
  fetchSyncAreaPaths,
  startAreaPathSync,
  updateSyncAreaPath,
} from "../services/syncServiceClient";
import type { AreaPathInput, SyncAreaPath } from "../services/syncServiceClient";

const POLL_INTERVAL_MS = 5_000;

interface FormState {
  organization: string;
  project: string;
  area_path: string;
  incluir_subpaths: boolean;
  ativo: boolean;
  intervalo_minutos: string;
}

const EMPTY_FORM: FormState = {
  organization: "",
  project: "",
  area_path: "",
  incluir_subpaths: true,
  ativo: true,
  intervalo_minutos: "60",
};

function toFormState(areaPath?: SyncAreaPath): FormState {
  if (!areaPath) {
    return EMPTY_FORM;
  }

  return {
    organization: areaPath.organization,
    project: areaPath.project,
    area_path: areaPath.area_path,
    incluir_subpaths: areaPath.incluir_subpaths,
    ativo: areaPath.ativo,
    intervalo_minutos: String(areaPath.intervalo_minutos),
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

function statusVariant(status: string | null): "neutral" | "success" | "warning" | "error" {
  if (status === "ok") {
    return "success";
  }
  if (status === "auth_error" || status === "error") {
    return "error";
  }
  return "neutral";
}

function StatusMessage({ areaPath }: { areaPath: SyncAreaPath }) {
  if (areaPath.last_sync_status === "ok") {
    return (
      <Banner
        status="success"
        title="Synchronization completed successfully"
        description={areaPath.last_sync_count === null ? undefined : `${areaPath.last_sync_count} work items synchronized.`}
      />
    );
  }

  if (areaPath.last_sync_status === "auth_error") {
    return (
      <Banner
        status="error"
        title="Synchronization requires Azure DevOps authentication"
        description={areaPath.last_error_msg ?? "Configure AZURE_DEVOPS_API_KEY and try again."}
      />
    );
  }

  if (areaPath.last_sync_status === "error") {
    return (
      <Banner
        status="error"
        title="Synchronization failed"
        description={areaPath.last_error_msg ?? "The synchronization service returned an error."}
      />
    );
  }

  return null;
}

export default function SynchronizationPage() {
  const [areaPaths, setAreaPaths] = useState<SyncAreaPath[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingAreaPath, setEditingAreaPath] = useState<SyncAreaPath | null | undefined>(undefined);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [isSaving, setIsSaving] = useState(false);
  const [deletingAreaPath, setDeletingAreaPath] = useState<SyncAreaPath | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [startingIds, setStartingIds] = useState<Set<number>>(new Set());
  const latestRequestId = useRef(0);
  const latestInitialLoadId = useRef(0);
  const isMounted = useRef(false);
  const pollingIds = useRef(new Map<number, boolean>());
  const pollingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef<() => Promise<void>>(async () => {});

  const clearPollingTimer = useCallback(() => {
    if (pollingTimer.current !== null) {
      clearTimeout(pollingTimer.current);
      pollingTimer.current = null;
    }
  }, []);

  const stopPolling = useCallback((areaPathId: number) => {
    pollingIds.current.delete(areaPathId);
    if (pollingIds.current.size === 0) {
      clearPollingTimer();
    }
  }, [clearPollingTimer]);

  const refresh = useCallback(async (): Promise<SyncAreaPath[] | null> => {
    const requestId = ++latestRequestId.current;
    try {
      const nextAreaPaths = await fetchSyncAreaPaths();
      if (!isMounted.current || requestId !== latestRequestId.current) {
        return null;
      }
      setAreaPaths(nextAreaPaths);
      setError(null);
      return nextAreaPaths;
    } catch (requestError) {
      if (isMounted.current && requestId === latestRequestId.current) {
        setError(errorMessage(requestError));
      }
      return null;
    }
  }, []);

  const schedulePolling = useCallback(() => {
    if (!isMounted.current || pollingIds.current.size === 0 || pollingTimer.current !== null) {
      return;
    }

    pollingTimer.current = setTimeout(() => {
      pollingTimer.current = null;
      void pollRef.current();
    }, POLL_INTERVAL_MS);
  }, []);

  const poll = useCallback(async () => {
    const nextAreaPaths = await refresh();
    if (!isMounted.current) {
      return;
    }

    if (nextAreaPaths !== null) {
      for (const [areaPathId, hasObservedRunning] of pollingIds.current) {
        const areaPath = nextAreaPaths.find((candidate) => candidate.id === areaPathId);
        if (!areaPath) {
          pollingIds.current.delete(areaPathId);
        } else if (areaPath.is_running) {
          pollingIds.current.set(areaPathId, true);
        } else if (hasObservedRunning && areaPath.last_sync_status !== null) {
          pollingIds.current.delete(areaPathId);
        }
      }
    }

    schedulePolling();
  }, [refresh, schedulePolling]);

  pollRef.current = poll;

  useEffect(() => {
    isMounted.current = true;
    const initialLoadId = ++latestInitialLoadId.current;

    void refresh().finally(() => {
      if (isMounted.current && initialLoadId === latestInitialLoadId.current) {
        setIsLoading(false);
      }
    });

    return () => {
      isMounted.current = false;
      ++latestRequestId.current;
      pollingIds.current.clear();
      clearPollingTimer();
    };
  }, [clearPollingTimer, refresh]);

  const openCreateDialog = () => {
    setForm(toFormState());
    setEditingAreaPath(null);
  };

  const openEditDialog = (areaPath: SyncAreaPath) => {
    setForm(toFormState(areaPath));
    setEditingAreaPath(areaPath);
  };

  const closeFormDialog = () => {
    setEditingAreaPath(undefined);
    setIsSaving(false);
  };

  const handleSubmit = async () => {
    const input: AreaPathInput = {
      organization: form.organization.trim(),
      project: form.project.trim(),
      area_path: form.area_path.trim(),
      incluir_subpaths: form.incluir_subpaths,
      ativo: form.ativo,
      intervalo_minutos: Number(form.intervalo_minutos),
    };

    setIsSaving(true);
    setError(null);
    try {
      if (editingAreaPath) {
        await updateSyncAreaPath(editingAreaPath.id, input);
      } else {
        await createSyncAreaPath(input);
      }
      closeFormDialog();
      await refresh();
    } catch (requestError) {
      setError(errorMessage(requestError));
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingAreaPath) {
      return;
    }

    setIsDeleting(true);
    setError(null);
    try {
      await deleteSyncAreaPath(deletingAreaPath.id);
      stopPolling(deletingAreaPath.id);
      setDeletingAreaPath(null);
      await refresh();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      if (isMounted.current) {
        setIsDeleting(false);
      }
    }
  };

  const handleStartSync = async (areaPathId: number) => {
    setStartingIds((current) => new Set(current).add(areaPathId));
    setError(null);
    try {
      await startAreaPathSync(areaPathId);
      pollingIds.current.set(areaPathId, false);
      await poll();
    } catch (requestError) {
      stopPolling(areaPathId);
      setError(errorMessage(requestError));
    } finally {
      if (isMounted.current) {
        setStartingIds((current) => {
          const next = new Set(current);
          next.delete(areaPathId);
          return next;
        });
      }
    }
  };

  const isFormOpen = editingAreaPath !== undefined;
  const isEditing = editingAreaPath !== null && editingAreaPath !== undefined;

  return (
    <VStack gap={4}>
      <HStack justify="between" align="center" wrap="wrap">
        <Text as="h1" type="display-3">Synchronization</Text>
        <Button label="Add area path" variant="primary" onClick={openCreateDialog} />
      </HStack>

      {error && <Banner status="error" title="Synchronization management error" description={error} />}

      {isLoading && <Spinner label="Loading synchronization settings" />}

      {!isLoading && areaPaths.length === 0 && (
        <EmptyState
          title="No area paths configured"
          description="Add an area path to start synchronizing Azure DevOps work items."
          actions={<Button label="Add area path" variant="primary" onClick={openCreateDialog} />}
        />
      )}

      {!isLoading && areaPaths.map((areaPath) => (
        <Card key={areaPath.id}>
          <VStack gap={3}>
            <HStack justify="between" align="center" wrap="wrap">
              <VStack gap={1}>
                <Text as="h2" type="large" weight="semibold">{areaPath.area_path}</Text>
                <Text type="supporting">{areaPath.organization} / {areaPath.project}</Text>
              </VStack>
              <HStack gap={2} align="center" wrap="wrap">
                <Badge
                  variant={areaPath.ativo ? "success" : "neutral"}
                  label={areaPath.ativo ? "Active" : "Inactive"}
                />
                <Badge
                  variant={areaPath.is_running ? "warning" : statusVariant(areaPath.last_sync_status)}
                  label={areaPath.is_running ? "Running" : areaPath.last_sync_status ?? "Not synchronized"}
                />
                <Button
                  label="Synchronize"
                  variant="primary"
                  isDisabled={areaPath.is_running || startingIds.has(areaPath.id)}
                  onClick={() => void handleStartSync(areaPath.id)}
                />
                <Button label={`Edit ${areaPath.area_path}`} onClick={() => openEditDialog(areaPath)} />
                <Button
                  label={`Delete ${areaPath.area_path}`}
                  variant="destructive"
                  onClick={() => setDeletingAreaPath(areaPath)}
                />
              </HStack>
            </HStack>
            <Text type="supporting">Every {areaPath.intervalo_minutos} minutes</Text>
            <Text type="supporting">Include subpaths: {areaPath.incluir_subpaths ? "Yes" : "No"}</Text>
            <Text type="supporting">Last synchronized: {areaPath.last_sync_at ?? "Never"}</Text>
            <Text type="supporting">Processed items: {areaPath.last_sync_count ?? 0}</Text>
            <Text type="supporting">Last sync count: {areaPath.last_sync_count ?? 0}</Text>
            <StatusMessage areaPath={areaPath} />
          </VStack>
        </Card>
      ))}

      <Dialog
        isOpen={isFormOpen}
        onOpenChange={(open) => !open && closeFormDialog()}
        purpose="form"
        width={560}
      >
        <DialogHeader
          title={isEditing ? "Edit area path" : "Add area path"}
          onOpenChange={(open) => !open && closeFormDialog()}
        />
        <VStack gap={3}>
          <TextInput
            label="Organization"
            value={form.organization}
            onChange={(organization) => setForm((current) => ({ ...current, organization }))}
            isRequired
          />
          <TextInput
            label="Project"
            value={form.project}
            onChange={(project) => setForm((current) => ({ ...current, project }))}
            isRequired
          />
          <TextInput
            label="Area path"
            value={form.area_path}
            onChange={(area_path) => setForm((current) => ({ ...current, area_path }))}
            isRequired
          />
          <TextInput
            label="Interval (minutes)"
            value={form.intervalo_minutos}
            onChange={(intervalo_minutos) => setForm((current) => ({ ...current, intervalo_minutos }))}
            isRequired
          />
          <Selector
            label="Include subpaths"
            value={String(form.incluir_subpaths)}
            onChange={(value) => setForm((current) => ({ ...current, incluir_subpaths: value === "true" }))}
            options={[
              { value: "true", label: "Yes" },
              { value: "false", label: "No" },
            ]}
          />
          <Selector
            label="Active"
            value={String(form.ativo)}
            onChange={(value) => setForm((current) => ({ ...current, ativo: value === "true" }))}
            options={[
              { value: "true", label: "Yes" },
              { value: "false", label: "No" },
            ]}
          />
          <HStack gap={2} justify="end">
            <Button label="Cancel" onClick={closeFormDialog} />
            <Button
              label={isEditing ? "Save changes" : "Create"}
              variant="primary"
              isLoading={isSaving}
              isDisabled={
                !form.organization.trim()
                || !form.project.trim()
                || !form.area_path.trim()
                || !Number.isFinite(Number(form.intervalo_minutos))
                || Number(form.intervalo_minutos) <= 0
              }
              onClick={() => void handleSubmit()}
            />
          </HStack>
        </VStack>
      </Dialog>

      <AlertDialog
        isOpen={deletingAreaPath !== null}
        onOpenChange={(open) => !open && setDeletingAreaPath(null)}
        title="Delete area path?"
        description={deletingAreaPath ? `Remove ${deletingAreaPath.area_path} and its synchronization configuration.` : ""}
        actionLabel="Delete"
        isActionLoading={isDeleting}
        onAction={() => void handleDelete()}
      />
    </VStack>
  );
}
