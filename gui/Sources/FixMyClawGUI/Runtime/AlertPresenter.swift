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
    typealias PresentationHook = @MainActor (
        AlertRequest,
        @escaping @MainActor (NSApplication.ModalResponse) -> Void
    ) -> Void

    static let shared = AlertPresenter()

    private var queue: [AlertRequest] = []
    private var isPresenting = false
    private var hostWindow: NSWindow?
    private let presentationHook: PresentationHook?

    init(presentationHook: PresentationHook? = nil) {
        self.presentationHook = presentationHook
    }

    var queuedRequestCount: Int { queue.count }
    var isPresentingAlert: Bool { isPresenting }

    func present(_ request: AlertRequest) {
        queue.append(request)
        presentNextIfNeeded()
    }

    private func presentNextIfNeeded() {
        guard !isPresenting, !queue.isEmpty else { return }

        isPresenting = true
        let request = queue.removeFirst()

        if let presentationHook {
            presentationHook(request) { [weak self] response in
                self?.finishPresentation(of: request, response: response)
            }
            return
        }

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
                self?.finishPresentation(
                    of: request,
                    response: response,
                    cleanup: {
                        window?.orderOut(nil)
                        window?.close()
                    }
                )
            }
        }
    }

    private func finishPresentation(
        of request: AlertRequest,
        response: NSApplication.ModalResponse,
        cleanup: @MainActor () -> Void = {}
    ) {
        request.completion(response)
        cleanup()
        hostWindow = nil
        isPresenting = false
        presentNextIfNeeded()
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
