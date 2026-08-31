//
//  SendToVisperIntent.swift
//  vIsper (iOS) — RASCUNHO, NUNCA COMPILADO
//
//  Escrito sem acesso a Xcode/SDK do iOS (o ambiente onde isso foi
//  gerado não tem como compilar nem rodar código Swift/iOS). Isso é
//  um ponto de partida pra continuar no Claude Code, num Mac de
//  verdade — não trate como testado.
//
//  Antes de considerar isso pronto:
//    1. Criar um projeto Xcode novo (App, iOS, SwiftUI) e adicionar
//       este arquivo a ele.
//    2. Confirmar que compila e que o App Intent aparece no app
//       Atalhos.
//    3. Trocar ntfyTopic abaixo pelo mesmo valor de NTFY_TOPIC em
//       config.py, no lado do Mac.
//    4. Testar de ponta a ponta: disparar pela Siri/Atalhos/Botão de
//       Ação e confirmar que chega no relay_listener.py do Mac.
//    5. Conferir especificamente se `command` é pedido/preenchido
//       direito ao disparar pelas duas primeiras frases (ver comentário
//       em VisperShortcuts abaixo) — terceira frase adicionada como
//       caminho alternativo mais garantido, mas nenhuma das três foi
//       testada de verdade ainda.
//    6. Dizer pra quem for usar: o `command` falado/ditado precisa
//       COMEÇAR com o nome de uma IA configurada (ex.: "Mandar claude
//       qual é a previsão do tempo pro vIsper") — perform() já gruda
//       a wake word no início e "over" no fim (ver abaixo), mas o
//       roteador do Mac (command_router.py) só abre uma IA se um nome
//       reconhecido vier logo depois da wake word; sem isso a mensagem
//       chega no Mac e não abre nada, sem erro nenhum (mesmo problema
//       documentado em ATALHO_IPHONE.md pro caminho do app Atalhos).
//
//  Verificado de rede (deste ambiente, sem Mac): tentei bater no
//  ntfy.sh de verdade pra validar as suposições de formato daqui
//  (POST sem Content-Type vira o texto da mensagem; resposta 200 em
//  caso de sucesso) contra a doc pública deles — mas o proxy de saída
//  deste sandbox BLOQUEIA ntfy.sh por política (não é específico
//  desse código, nenhuma ferramenta consegue sair pra lá daqui). As
//  suposições batem com a documentação pública do ntfy, mas continuam
//  sem confirmação de rede de verdade — só dá pra validar isso a
//  partir do Mac/rede da Valeta mesmo, nunca de um sandbox como este.
//
//  O que isso faz: expõe uma ação ("Mandar pro vIsper") disparável
//  pela Siri, pelo Botão de Ação (iPhone 15 Pro+), ou por um atalho
//  na tela de início. Pega o texto (ditado pra Siri ou passado por
//  um Atalho) e publica ele no mesmo tópico ntfy que o Mac está
//  ouvindo — o Mac trata esse texto exatamente como trataria uma
//  transcrição local (ver relay_listener.py + dictation.py).
//

import AppIntents
import Foundation

struct SendToVisperIntent: AppIntent {
    static var title: LocalizedStringResource = "Mandar comando pro vIsper"
    static var description = IntentDescription(
        "Manda um comando de voz pro vIsper no Mac, de qualquer lugar."
    )

    @Parameter(title: "Comando")
    var command: String

    // TODO antes de usar de verdade: tirar esse hardcode daqui.
    // Ideias: tela simples de config dentro do app, ou Keychain.
    // Tem que ser o MESMO valor de NTFY_TOPIC em config.py (Mac) — ou,
    // mais precisamente, o valor de VERDADE (settings.json ou o link
    // impresso por setup_visper.py — config.py em si SEMPRE mostra ""
    // no repositório, ver ATALHO_IPHONE.md pro mesmo erro já corrigido
    // lá).
    private let ntfyServer = "https://ntfy.sh"
    private let ntfyTopic = "TROQUE_AQUI_PELO_MESMO_TOPICO_DO_MAC"

    // Tem que bater com WAKE_WORD em config.py (Mac) — "vIsper" é o
    // padrão de lá. Trocar aqui SE E SÓ SE tiver trocado por lá
    // também (menu "Wake word…" do app do Mac).
    private let wakeWord = "vIsper"

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let url = URL(string: "\(ntfyServer)/\(ntfyTopic)") else {
            return .result(dialog: "Não consegui montar o endereço do vIsper.")
        }

        // O pipeline do Mac (command_router.py + dictation.py) espera
        // a wake word NO INÍCIO e um gatilho de fechamento NO FIM de
        // toda mensagem completa — sem os dois, `command` sozinho
        // nunca bate com nada: command_router._decide() procura a wake
        // word primeiro e desiste na hora se ela não estiver lá (ver
        // CLAUDE.md). Bug real que isso corrige: a versão anterior
        // mandava `command` puro, então o recurso não funcionava NEM
        // UMA VEZ, mesmo compilado e mesmo com o parâmetro `command`
        // capturado certinho pela Siri — faltava isto, não o
        // binding do parâmetro.
        let mensagem = "\(wakeWord) \(command) over"

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.httpBody = mensagem.data(using: .utf8)

        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                return .result(dialog: "O vIsper não confirmou o recebimento.")
            }
            return .result(dialog: "Mandado pro vIsper.")
        } catch {
            return .result(dialog: "Sem conexão — não deu pra mandar agora.")
        }
    }
}

// Registra a frase que a Siri reconhece e o ícone/nome que aparece
// no app Atalhos.
//
// ATENÇÃO — checar isso especificamente ao compilar num Mac de
// verdade: nenhuma das duas primeiras frases captura o parâmetro
// `command` (não têm `\(\.$command)` embutido) — a suposição era que
// o sistema pergunta o valor que falta automaticamente depois (fluxo
// padrão de follow-up prompt do App Intents pra parâmetro obrigatório
// não capturado na frase), mas isso NUNCA foi confirmado rodando de
// verdade (nem tinha como, sem Xcode). Adicionei uma terceira frase
// que captura `command` diretamente (`\(\.$command)`) como caminho
// mais garantido — testar as três no app Atalhos; se as duas
// primeiras não pedirem o texto direito, pode ser questão de manter
// só a terceira.
struct VisperShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: SendToVisperIntent(),
            phrases: [
                "Mandar pro \(.applicationName)",
                "\(.applicationName) manda isso",
                "Mandar \(\.$command) pro \(.applicationName)",
            ],
            shortTitle: "Mandar pro vIsper",
            systemImageName: "mic.circle.fill"
        )
    }
}
