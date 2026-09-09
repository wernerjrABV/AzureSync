import { useCallback, useEffect, useRef, useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Divider } from "@astryxdesign/core/Divider";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Grid } from "@astryxdesign/core/Grid";
import { Icon } from "@astryxdesign/core/Icon";
import { IconButton } from "@astryxdesign/core/IconButton";
import {
  Card,
  HStack,
  VStack,
} from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import AzureDevOpsCredentialCard from "../components/AzureDevOpsCredentialCard";
import {
  createSyncAreaPath,
  cancelAllSyncs,
  cancelAreaPathSync,
  deleteSyncAreaPath,
  fetchSyncAreaPaths,
  forceAreaPathSync,
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
  if (status === "cancelled") {
    return "warning";
  }
  return "neutral";
}

function formatInterval(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (hours === 0) {
    return `${remainingMinutes} min`;
  }
  if (remainingMinutes === 0) {
    return `${hours}h`;
  }
  return `${hours}h ${remainingMinutes}m`;
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
        description={
          areaPath.last_error_msg
            ?? "Update the Azure DevOps credential on this page and try again."
        }
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

  if (areaPath.last_sync_status === "cancelled") {
    return (
      <Banner
        status="warning"
        title="Synchronization cancelled"
        description="The synchronization was stopped before it completed."
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
  const [cancellingAreaPath, setCancellingAreaPath] = useState<SyncAreaPath | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isCancelAllOpen, setIsCancelAllOpen] = useState(false);
  const [forcingAreaPath, setForcingAreaPath] = useState<SyncAreaPath | null>(null);
  const [isForcing, setIsForcing] = useState(false);
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
          setStartingIds((current) => {
            const next = new Set(current);
            next.delete(areaPathId);
            return next;
          });
        } else if (areaPath.is_running) {
          pollingIds.current.set(areaPathId, true);
        } else if (hasObservedRunning && areaPath.last_sync_status !== null) {
          pollingIds.current.delete(areaPathId);
          setStartingIds((current) => {
            const next = new Set(current);
            next.delete(areaPathId);
            return next;
          });
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
    setAreaPaths((current) => current.map((areaPath) => (
      areaPath.id === areaPathId
        ? { ...areaPath, is_running: true }
        : areaPath
    )));
    setError(null);
    try {
      await startAreaPathSync(areaPathId);
      pollingIds.current.set(areaPathId, false);
      await poll();
    } catch (requestError) {
      stopPolling(areaPathId);
      setAreaPaths((current) => current.map((areaPath) => (
        areaPath.id === areaPathId
          ? { ...areaPath, is_running: false }
          : areaPath
      )));
      setError(errorMessage(requestError));
    } finally {
      if (isMounted.current && !pollingIds.current.has(areaPathId)) {
        setStartingIds((current) => {
          const next = new Set(current);
          next.delete(areaPathId);
          return next;
        });
      }
    }
  };

  const handleStartAllSyncs = async () => {
    const availableAreaPathIds = areaPaths
      .filter((areaPath) => !areaPath.is_running && !startingIds.has(areaPath.id))
      .map((areaPath) => areaPath.id);

    await Promise.all(availableAreaPathIds.map((areaPathId) => handleStartSync(areaPathId)));
  };

  const handleCancel = async () => {
    if (!cancellingAreaPath) {
      return;
    }

    setIsCancelling(true);
    setError(null);
    try {
      await cancelAreaPathSync(cancellingAreaPath.id);
      pollingIds.current.set(cancellingAreaPath.id, true);
      await poll();
      setCancellingAreaPath(null);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      if (isMounted.current) {
        setIsCancelling(false);
      }
    }
  };

  const handleCancelAll = async () => {
    setIsCancelling(true);
    setError(null);
    try {
      await cancelAllSyncs();
      for (const areaPath of areaPaths) {
        if (areaPath.is_running || startingIds.has(areaPath.id)) {
          pollingIds.current.set(areaPath.id, true);
        }
      }
      await poll();
      setIsCancelAllOpen(false);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      if (isMounted.current) {
        setIsCancelling(false);
      }
    }
  };

  const handleForceSync = async () => {
    if (!forcingAreaPath) {
      return;
    }

    setIsForcing(true);
    setError(null);
    try {
      await forceAreaPathSync(forcingAreaPath.id);
      setForcingAreaPath(null);
      setStartingIds((current) => new Set(current).add(forcingAreaPath.id));
      pollingIds.current.set(forcingAreaPath.id, false);
      await poll();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      if (isMounted.current) {
        setIsForcing(false);
      }
    }
  };

  const hasAvailableAreaPaths = areaPaths.some(
    (areaPath) => !areaPath.is_running && !startingIds.has(areaPath.id),
  );
  const hasRunningAreaPaths = areaPaths.some(
    (areaPath) => areaPath.is_running || startingIds.has(areaPath.id),
  );

  const isFormOpen = editingAreaPath !== undefined;
  const isEditing = editingAreaPath !== null && editingAreaPath !== undefined;

  return (
    <VStack gap={4}>
      <HStack justify="between" align="center" wrap="wrap">
        <Text as="h1" type="display-3">Synchronization</Text>
        <HStack gap={2} wrap="wrap">
          <Button
            label="Synchronize all"
            variant="primary"
            isDisabled={!hasAvailableAreaPaths}
            onClick={() => void handleStartAllSyncs()}
          />
          <Button
            label="Cancel all"
            variant="destructive"
            isDisabled={!hasRunningAreaPaths || isCancelling}
            onClick={() => setIsCancelAllOpen(true)}
          />
          <Button label="Add area path" variant="primary" onClick={openCreateDialog} />
        </HStack>
      </HStack>

      {error && <Banner status="error" title="Synchronization management error" description={error} />}

      <AzureDevOpsCredentialCard />

      {isLoading && <Spinner label="Loading synchronization settings" />}

      {!isLoading && areaPaths.length === 0 && (
        <EmptyState
          title="No area paths configured"
          description="Add an area path to start synchronizing Azure DevOps work items."
          actions={<Button label="Add area path" variant="primary" onClick={openCreateDialog} />}
        />
      )}

      {!isLoading && areaPaths.length > 0 && (
        <Grid
          data-testid="synchronization-card-grid"
          columns={{ minWidth: 280, max: 3 }}
          gap={4}
        >
          {areaPaths.map((areaPath) => (
            <Card key={areaPath.id} padding={3} height="100%">
                <VStack gap={3} height="100%" justify="between">
                <VStack gap={1}>
                    <HStack justify="end" align="center">
                      <Badge
                        variant={areaPath.ativo ? "success" : "neutral"}
                        label={areaPath.ativo ? "Active" : "Inactive"}
                      />
                    </HStack>
                    <Text as="h2" type="large" weight="semibold">{areaPath.area_path}</Text>
                    <Text type="supporting">{areaPath.organization} / {areaPath.project}</Text>
                    <HStack gap={2} align="center" wrap="wrap">
                      <Badge
                        variant={areaPath.is_running || startingIds.has(areaPath.id) ? "warning" : statusVariant(areaPath.last_sync_status)}
                        label={areaPath.is_running || startingIds.has(areaPath.id) ? "Running" : areaPath.last_sync_status ?? "Not synchronized"}
                      />
                      <Text type="supporting">Every {formatInterval(areaPath.intervalo_minutos)}</Text>
                    </HStack>
                </VStack>
                <VStack gap={2}>
                  <Text type="supporting">Include subpaths: {areaPath.incluir_subpaths ? "Yes" : "No"}</Text>
                  <Text type="supporting">Last synchronized: {areaPath.last_sync_at ?? "Never"}</Text>
                  <Text type="supporting">Last sync count: {areaPath.last_sync_count ?? 0}</Text>
                  <StatusMessage areaPath={areaPath} />
                </VStack>
                <VStack gap={2}>
                  <Divider />
                  <HStack gap={2} justify="end" align="center">
                      <IconButton
                    label={`Synchronize ${areaPath.area_path}`}
                    tooltip="Synchronize"
                    icon={<Icon icon="arrowsUpDown" size="sm" />}
                    variant="primary"
                    isDisabled={areaPath.is_running || startingIds.has(areaPath.id)}
                    onClick={() => void handleStartSync(areaPath.id)}
                  />
                  {(areaPath.is_running || startingIds.has(areaPath.id)) && (
                    <IconButton
                      label={`Cancel ${areaPath.area_path}`}
                      tooltip="Cancel synchronization"
                      icon={<Icon icon="stop" size="sm" />}
                      variant="destructive"
                      isDisabled={isCancelling}
                      onClick={() => setCancellingAreaPath(areaPath)}
                    />
                  )}
                  {(areaPath.is_running || startingIds.has(areaPath.id)) && (
                    <Button
                      label="Force synchronization"
                      variant="secondary"
                      isDisabled={isForcing}
                      onClick={() => setForcingAreaPath(areaPath)}
                    />
                  )}
                  <IconButton
                    label={`Edit ${areaPath.area_path}`}
                    tooltip="Edit"
                    icon={<Icon icon={Pencil} size="sm" />}
                    isDisabled={areaPath.is_running || startingIds.has(areaPath.id)}
                    onClick={() => openEditDialog(areaPath)}
                  />
                  <IconButton
                    label={`Delete ${areaPath.area_path}`}
                    tooltip="Delete"
                    icon={<Icon icon={Trash2} size="sm" />}
                    variant="destructive"
                    isDisabled={areaPath.is_running || startingIds.has(areaPath.id)}
                    onClick={() => setDeletingAreaPath(areaPath)}
                  />
                  </HStack>
                </VStack>
              </VStack>
            </Card>
          ))}
        </Grid>
      )}

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
            description="Found in the Azure DevOps URL: https://dev.azure.com/{organization}."
            value={form.organization}
            onChange={(organization) => setForm((current) => ({ ...current, organization }))}
            isRequired
          />
          <TextInput
            label="Project"
            description="The project name from the Azure DevOps URL, or the project selector in the top navigation."
            value={form.project}
            onChange={(project) => setForm((current) => ({ ...current, project }))}
            isRequired
          />
          <TextInput
            label="Area path"
            description="Copy the exact hierarchy from Project settings > Boards > Areas, for example Project\\Team."
            value={form.area_path}
            onChange={(area_path) => setForm((current) => ({ ...current, area_path }))}
            isRequired
          />
          <TextInput
            label="Interval (minutes)"
            description="How often this area path is synchronized automatically."
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

      <AlertDialog
        isOpen={cancellingAreaPath !== null}
        onOpenChange={(open) => !open && !isCancelling && setCancellingAreaPath(null)}
        title="Cancel synchronization?"
        description={cancellingAreaPath ? `Stop synchronization for ${cancellingAreaPath.area_path}?` : ""}
        actionLabel="Cancel synchronization"
        isActionLoading={isCancelling}
        onAction={() => void handleCancel()}
      />

      <AlertDialog
        isOpen={isCancelAllOpen}
        onOpenChange={(open) => !open && !isCancelling && setIsCancelAllOpen(false)}
        title="Cancel all synchronizations?"
        description="Stop every synchronization currently running or waiting to start."
        actionLabel="Cancel all"
        isActionLoading={isCancelling}
        onAction={() => void handleCancelAll()}
      />

      <AlertDialog
        isOpen={forcingAreaPath !== null}
        onOpenChange={(open) => !open && !isForcing && setForcingAreaPath(null)}
        title="Force synchronization?"
        description={forcingAreaPath ? `Reset a stale synchronization lock for ${forcingAreaPath.area_path} and start it again? Use this only when the synchronization is no longer running.` : ""}
        actionLabel="Force synchronization"
        isActionLoading={isForcing}
        onAction={() => void handleForceSync()}
      />
    </VStack>
  );
}
