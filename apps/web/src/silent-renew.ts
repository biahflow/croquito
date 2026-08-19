/**
 * Entry do iframe de renovação silenciosa: entrega a URL de retorno ao `UserManager` do
 * pai e nada mais. Um `UserManager` vazio basta — o `signinSilentCallback` só lê a URL
 * corrente e a repassa por `postMessage`; quem valida `state` e troca o código é o
 * gerenciador da janela principal.
 */
import { UserManager } from "oidc-client-ts";

void new UserManager({
  authority: "",
  client_id: "",
  redirect_uri: "",
}).signinSilentCallback();
