<#--
  Layout dos e-mails HTML do tema `croquito`. Sobrescreve `base/email/html/template.ftl`,
  que é literalmente `<html><body><#nested></body></html>` — sem marca, sem tipografia,
  sem margem.

  Só o VESTUÁRIO entra aqui. O texto de cada e-mail continua vindo das mensagens do
  Keycloak, via `<#nested>`: copy de e-mail é F-008 e tem gate humano próprio
  (docs/features/F-007-tela-de-login/mock/README.md).

  Por que tabela e estilo inline, e não folha de estilo: cliente de e-mail não carrega
  recurso de tema (`url.resourcesPath` não existe no contexto de e-mail) e boa parte deles
  descarta `<style>` no `<head>`. Tabela com atributo e `style=` no elemento é o que
  atravessa Outlook, Gmail e cliente de celular.

  A marca é desenhada com caixa e borda, não com imagem: o símbolo do Croquito é um quadrado
  vetorial verde sobre grafite, e reproduzi-lo em CSS evita imagem bloqueada por padrão
  (quase todo cliente bloqueia imagem remota até a pessoa autorizar) — justamente no e-mail
  em que ela ainda não confia no remetente.

  Cor: tokens de docs/engineering/DESIGN_SYSTEM.md. `--accent` (#00c877) aparece só em
  traço/preenchimento do símbolo; texto verde seria `--accent-text` (#00744a), e não há
  texto verde aqui.
-->
<#macro emailLayout>
<html lang="${locale.language}" dir="${(ltr)?then('ltr','rtl')}">
<head>
  <meta charset="utf-8">
  <meta name="color-scheme" content="light">
  <#--
    O corpo do e-mail vem das mensagens do Keycloak, e o `<a>` dele não tem classe nem
    `style` para a gente pôr a cor da marca. Sem esta folha o link sai no azul padrão do
    cliente de e-mail. Ela é a única saída possível aqui, e é parcial de propósito: um
    cliente que descarta `<style>` mostra o link azul — legível, só não da marca. Verde de
    TEXTO é `--accent-text` (#00744a, 5,8:1), nunca `--accent`.
  -->
  <style>
    a { color: #00744a !important; text-decoration: underline; }
    p { margin: 0 0 14px; }
  </style>
</head>
<body style="margin:0;padding:0;background-color:#efefeb;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#efefeb;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
               style="max-width:520px;background-color:#ffffff;border:1px solid #e5e5e0;
                      border-radius:13px;">
          <tr>
            <td style="padding:30px 30px 0;" align="center">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td width="40" height="40" align="center" valign="middle"
                      style="width:40px;height:40px;background-color:#0e1116;border-radius:9px;">
                    <div style="width:16px;height:16px;border:5px solid #00c877;font-size:0;
                                line-height:0;">&nbsp;</div>
                  </td>
                </tr>
              </table>
              <div style="margin-top:12px;font-family:Georgia,'Times New Roman',serif;
                          font-size:20px;font-weight:600;color:#14181d;">Croquito</div>
            </td>
          </tr>
          <tr>
            <td style="padding:22px 30px 30px;font-family:Inter,'Segoe UI',Helvetica,Arial,
                       sans-serif;font-size:14px;line-height:1.62;color:#14181d;">
              <#nested>
            </td>
          </tr>
          <tr>
            <td style="padding:0 30px 26px;">
              <div style="border-top:1px solid #e5e5e0;font-size:0;line-height:0;">&nbsp;</div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
</#macro>
