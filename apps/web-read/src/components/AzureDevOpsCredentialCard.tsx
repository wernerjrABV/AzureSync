import { useEffect, useState } from "react";
import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Link } from "@astryxdesign/core/Link";
import { Card, HStack, VStack } from "@astryxdesign/core/Layout";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import {
  deleteAzureDevOpsCredential,
  fetchAzureDevOpsCredentialStatus,
  saveAzureDevOpsCredential,
} from "../services/syncServiceClient";
import type { AzureDevOpsCredentialStatus } from "../services/syncServiceClient";

const MAX_API_KEY_LENGTH = 4096;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}

export default function AzureDevOpsCredentialCard() {
  const [status, setStatus] = useState<AzureDevOpsCredentialStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<{ title: string; description: string } | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isRemoving, setIsRemoving] = useState(false);
  const [isConfirmRemoveOpen, setIsConfirmRemoveOpen] = useState(false);

  useEffect(() => {
    let active = true;

    fetchAzureDevOpsCredentialStatus()
      .then((nextStatus) => {
        if (active) {
          setStatus(nextStatus);
          setError(null);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError({
            title: "Unable to load credential status",
            description: errorMessage(loadError),
          });
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const nextStatus = await saveAzureDevOpsCredential(apiKey);
      setApiKey("");
      setStatus(nextStatus);
      setSuccess("Azure DevOps credential saved.");
    } catch (saveError) {
      setError({
        title: "Unable to save credential",
        description: errorMessage(saveError),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleRemove = async () => {
    setIsRemoving(true);
    setError(null);
    setSuccess(null);

    try {
      await deleteAzureDevOpsCredential();
      setStatus({
        configured: false,
        updated_at: null,
      });
      setApiKey("");
      setIsConfirmRemoveOpen(false);
      setSuccess("Azure DevOps credential removed.");
    } catch (removeError) {
      setError({
        title: "Unable to remove credential",
        description: errorMessage(removeError),
      });
    } finally {
      setIsRemoving(false);
    }
  };

  const isSaveDisabled = isLoading || isSaving || !apiKey.trim() || apiKey.length > MAX_API_KEY_LENGTH;
  const isRemoveDisabled = isLoading || isRemoving || !status?.configured;

  return (
    <Card padding={3}>
      <VStack gap={3}>
        <HStack justify="between" align="center" wrap="wrap">
          <Text as="h2" type="large" weight="semibold">Azure DevOps credential</Text>
          <Badge
            variant={status?.configured ? "success" : "warning"}
            label={status?.configured ? "Configured" : "Not configured"}
          />
        </HStack>

        {isLoading && <Spinner label="Loading Azure DevOps credential status" />}

        {status?.updated_at && (
          <Text type="supporting">Updated at {status.updated_at}</Text>
        )}

        <VStack gap={1}>
          <Text>
            To create a PAT, open{' '}
            <Link
              href="https://app.vssps.visualstudio.com/app/register"
              isExternalLink
            >
              Azure DevOps Personal access tokens
            </Link>
            , select <strong>+ New Token</strong>, choose the organization where the
            project lives, set an expiration date, and select <strong>Work Items (Read)</strong>.
          </Text>
          <Text type="supporting">
            This permission lets AzureSync read work items, area paths, and revision history.
            Copy the token when it is created; Azure DevOps shows it only once.{' '}
            <Link
              href="https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate"
              isExternalLink
            >
              See Microsoft&apos;s PAT guide
            </Link>
            .
          </Text>
        </VStack>

        {error && (
          <Banner
            status="error"
            title={error.title}
            description={error.description}
          />
        )}

        {success && (
          <Banner
            status="success"
            title={success}
          />
        )}

        <TextInput
          type="password"
          label="Azure DevOps personal access token"
          description="The token is encrypted for your Windows user and is never shown again."
          value={apiKey}
          onChange={(value) => {
            setApiKey(value);
            setError(null);
            setSuccess(null);
          }}
          isRequired
          isDisabled={isLoading || isSaving || isRemoving}
        />

        <HStack gap={2} justify="end">
          <Button
            label="Remove credential"
            variant="destructive"
            isDisabled={isRemoveDisabled}
            onClick={() => setIsConfirmRemoveOpen(true)}
          />
          <Button
            label="Save credential"
            variant="primary"
            isLoading={isSaving}
            isDisabled={isSaveDisabled}
            onClick={() => void handleSave()}
          />
        </HStack>
      </VStack>

      <AlertDialog
        isOpen={isConfirmRemoveOpen}
        onOpenChange={setIsConfirmRemoveOpen}
        title="Remove Azure DevOps credential?"
        description="This removes the saved Azure DevOps credential for the current Windows user."
        actionLabel="Remove credential"
        isActionLoading={isRemoving}
        onAction={() => void handleRemove()}
      />
    </Card>
  );
}
