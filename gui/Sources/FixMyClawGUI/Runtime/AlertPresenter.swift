import AppKit
import SwiftUI

@MainActor
struct AlertRequest {
    let windowTitle: String
    let messageText: String
    let informativeText: String
    let style: NSAlert.Style
    let buttonTitles: [String]
    let completion: @MainActor (NSApplication.ModalResponse) -> Void
}

/// AlertPresenter 统一负责非阻塞 alert sheet 的排队与展示。
@MainActor
final class AlertPresenter {
    static let shared = AlertPresenter()

    private var queue: [AlertRequest] = []
    private var isPresenting = false
    private var hostWindow: NSWindow?

    private init() {}

    func present(_ request: AlertRequest) {
        queue.append(request)
        presentNextIfNeeded()
    }

    private func presentNextIfNeeded() {
        guard !isPresenting, !queue.isEmpty else { return }

        isPresenting = true
        let request = queue.removeFirst()
        let window = makeHostWindow(title: request.windowTitle)
        hostWindow = window

        let alert = NSAlert()
        alert.alertStyle = request.style
        alert.messageText = request.messageText
        alert.informativeText = request.informativeText
        request.buttonTitles.forEach { alert.addButton(withTitle: $0) }

        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        alert.beginSheetModal(for: window) { [weak self, weak window] response in
            Task { @MainActor [weak self, weak window] in
                request.completion(response)
                window?.orderOut(nil)
                window?.close()
                self?.hostWindow = nil
                self?.isPresenting = false
                self?.presentNextIfNeeded()
            }
        }
    }

    private func makeHostWindow(title: String) -> NSWindow {
        let controller = NSHostingController(rootView: EmptyView())
        let window = NSWindow(contentViewController: controller)
        window.title = title
        window.setContentSize(NSSize(width: 420, height: 180))
        window.styleMask = [.titled]
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isReleasedWhenClosed = false
        window.center()
        return window
    }
}
