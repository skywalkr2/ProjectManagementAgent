// The name a person gave an AI account, for the screens that name one (Today's lines, the header's status): the account's
// id in the settings is never shown. Until the list has loaded, or for an account it doesn't know, the id stands in so
// nothing is blank.
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { accountName } from "./ai-accounts";
import { useWords } from "./wording";

export function useAccountNames(): (id: string) => string {
  const { t } = useWords();
  const accounts = useQuery({ queryKey: ["ai-accounts"], queryFn: api.aiAccounts });
  const endpoints = useQuery({ queryKey: ["ai-endpoints"], queryFn: api.endpoints });
  return (id: string) => {
    const found = accounts.data?.find((a) => a.name === id);
    return found ? accountName(found, endpoints.data?.find((e) => e.id === found.kind), t) : id;
  };
}
