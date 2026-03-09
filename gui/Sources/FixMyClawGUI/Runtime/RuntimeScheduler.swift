import Darwin
import Dispatch
import Foundation

/// RuntimeScheduler 收敛 GUI runtime 的周期任务和状态目录观察。
@MainActor
final class RuntimeScheduler {
    private final class PeriodicTask: @unchecked Sendable {
        private let baseInterval: TimeInterval
        private let maxInterval: TimeInterval
        private let action: @MainActor @Sendable () async -> Bool

        private var timer: Timer?
        private var currentInterval: TimeInterval

        init(
            baseInterval: TimeInterval,
            maxInterval: TimeInterval,
            action: @escaping @MainActor @Sendable () async -> Bool
        ) {
            self.baseInterval = baseInterval
            self.maxInterval = maxInterval
            self.currentInterval = baseInterval
            self.action = action
        }

        func start() {
            currentInterval = baseInterval
            schedule(after: baseInterval)
        }

        func stop() {
            timer?.invalidate()
            timer = nil
            currentInterval = baseInterval
        }

        private func schedule(after interval: TimeInterval) {
            timer?.invalidate()
            timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: false) { [weak self] _ in
                self?.execute()
            }
        }

        private func execute() {
            timer?.invalidate()
            timer = nil

            Task { @MainActor [weak self] in
                guard let self else { return }
                let succeeded = await action()
                currentInterval = succeeded ? baseInterval : min(currentInterval * 2, maxInterval)
                schedule(after: currentInterval)
            }
        }
    }

    private final class StateDirectoryObserver: @unchecked Sendable {
        private var descriptor: CInt = -1
        private var source: DispatchSourceFileSystemObject?
        private var observedPath: String?
        private var debounceWorkItem: DispatchWorkItem?

        func start(directoryURL: URL, onChange: @escaping @MainActor @Sendable () -> Void) {
            let path = directoryURL.path
            guard observedPath != path || source == nil else { return }

            stop()

            guard FileManager.default.fileExists(atPath: path) else {
                observedPath = path
                return
            }

            let fd = Darwin.open(path, O_EVTONLY)
            guard fd != -1 else {
                observedPath = path
                return
            }

            let source = DispatchSource.makeFileSystemObjectSource(
                fileDescriptor: fd,
                eventMask: [.write, .delete, .rename, .extend, .attrib, .link, .revoke],
                queue: DispatchQueue.global(qos: .utility)
            )

            source.setEventHandler { [weak self] in
                self?.debounceWorkItem?.cancel()
                let workItem = DispatchWorkItem {
                    Task { @MainActor in
                        onChange()
                    }
                }
                self?.debounceWorkItem = workItem
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: workItem)
            }

            source.setCancelHandler { [weak self] in
                guard let self else { return }
                if descriptor != -1 {
                    Darwin.close(descriptor)
                    descriptor = -1
                }
            }

            observedPath = path
            descriptor = fd
            self.source = source
            source.resume()
        }

        func stop() {
            debounceWorkItem?.cancel()
            debounceWorkItem = nil

            source?.cancel()
            source = nil

            if descriptor != -1 {
                Darwin.close(descriptor)
                descriptor = -1
            }

            observedPath = nil
        }
    }

    private var statusTask: PeriodicTask?
    private var healthTask: PeriodicTask?
    private let stateDirectoryObserver = StateDirectoryObserver()

    func start(
        statusAction: @escaping @MainActor @Sendable () async -> Bool,
        healthAction: @escaping @MainActor @Sendable () async -> Bool,
        stateDirectoryURL: URL?,
        fileChangeHandler: @escaping @MainActor @Sendable () -> Void
    ) {
        stop()

        statusTask = PeriodicTask(baseInterval: 30, maxInterval: 300, action: statusAction)
        healthTask = PeriodicTask(baseInterval: 300, maxInterval: 1800, action: healthAction)

        statusTask?.start()
        healthTask?.start()

        refreshStateObservation(directoryURL: stateDirectoryURL, onChange: fileChangeHandler)
    }

    func refreshStateObservation(directoryURL: URL?, onChange: @escaping @MainActor @Sendable () -> Void) {
        guard let directoryURL else {
            stateDirectoryObserver.stop()
            return
        }
        stateDirectoryObserver.start(directoryURL: directoryURL, onChange: onChange)
    }

    func stop() {
        statusTask?.stop()
        healthTask?.stop()
        statusTask = nil
        healthTask = nil
        stateDirectoryObserver.stop()
    }

    func refreshNow(
        statusAction: @escaping @MainActor @Sendable () async -> Bool,
        healthAction: @escaping @MainActor @Sendable () async -> Bool
    ) {
        Task { @MainActor in
            _ = await statusAction()
            _ = await healthAction()
        }
    }
}
