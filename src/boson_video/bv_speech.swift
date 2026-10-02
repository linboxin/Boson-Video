// bv-speech: Apple's on-device speech-to-text (SpeechAnalyzer, macOS 26+) for boson-video.
//
//   bv-speech locales                      {"supported": [...], "installed": [...]}
//   bv-speech install <locale>             downloads the model if needed (progress on stderr)
//   bv-speech transcribe <audio> <locale>  one JSON object per line: {"start","end","text"}
//
// speech.py compiles this file on first use and keeps the binary in the user's cache.

import AVFoundation
import Foundation
import Speech

@main
struct BVSpeech {
    static func main() async {
        let args = CommandLine.arguments
        do {
            switch args.count > 1 ? args[1] : "" {
            case "locales":
                try await locales()
            case "install" where args.count > 2:
                try await install(Locale(identifier: args[2]))
            case "transcribe" where args.count > 3:
                try await transcribe(path: args[2], locale: Locale(identifier: args[3]))
            default:
                fail("usage: bv-speech locales | install <locale> | transcribe <audio> <locale>", code: 2)
            }
        } catch {
            fail("bv-speech: \(error)", code: 1)
        }
    }

    static func fail(_ message: String, code: Int32) -> Never {
        FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
        exit(code)
    }

    static func emit<T: Encodable>(_ value: T) {
        let data = try! JSONEncoder().encode(value)
        print(String(data: data, encoding: .utf8)!)
        fflush(stdout)
    }

    static func locales() async throws {
        struct Out: Encodable { let supported: [String]; let installed: [String] }
        let supported = await SpeechTranscriber.supportedLocales.map(\.identifier).sorted()
        let installed = await SpeechTranscriber.installedLocales.map(\.identifier).sorted()
        emit(Out(supported: supported, installed: installed))
    }

    static func install(_ locale: Locale) async throws {
        let transcriber = SpeechTranscriber(
            locale: locale, transcriptionOptions: [], reportingOptions: [], attributeOptions: [])
        if let request = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
            let progress = request.progress
            let reporter = Task {
                while !Task.isCancelled {
                    let pct = Int(progress.fractionCompleted * 100)
                    FileHandle.standardError.write("downloading \(locale.identifier): \(pct)%\n".data(using: .utf8)!)
                    try? await Task.sleep(for: .seconds(2))
                }
            }
            try await request.downloadAndInstall()
            reporter.cancel()
        }
        emit(["installed": locale.identifier])
    }

    static func transcribe(path: String, locale: Locale) async throws {
        struct Segment: Encodable { let start: Double; let end: Double; let text: String }
        let transcriber = SpeechTranscriber(
            locale: locale, transcriptionOptions: [], reportingOptions: [], attributeOptions: [.audioTimeRange])
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        let file = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        let collector = Task {
            for try await result in transcriber.results {
                let text = String(result.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
                if !text.isEmpty {
                    emit(Segment(start: result.range.start.seconds, end: result.range.end.seconds, text: text))
                }
            }
        }
        if let last = try await analyzer.analyzeSequence(from: file) {
            try await analyzer.finalizeAndFinish(through: last)
        } else {
            await analyzer.cancelAndFinishNow()
        }
        try await collector.value
    }
}
