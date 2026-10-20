# Java Multithreading and Concurrency

## Thread Creation

### Extending Thread
```java
public class MyThread extends Thread {
    @Override
    public void run() {
        System.out.println("Thread running: " + getName());
    }
}

MyThread t = new MyThread();
t.start();
```

### Implementing Runnable
```java
Runnable task = () -> {
    System.out.println("Runnable running");
};
new Thread(task).start();
```

### Callable and Future
```java
Callable<Integer> callable = () -> {
    Thread.sleep(1000);
    return 42;
};

ExecutorService executor = Executors.newSingleThreadExecutor();
Future<Integer> future = executor.submit(callable);
Integer result = future.get(); // Blocks until done
executor.shutdown();
```

## Synchronization

```java
// Synchronized method
public synchronized void increment() {
    count++;
}

// Synchronized block
public void update() {
    synchronized (this) {
        count++;
    }
}

// Static synchronized
public static synchronized void staticMethod() {
    // Locks on class object
}
```

## Locks

```java
private final ReentrantLock lock = new ReentrantLock();

public void safeMethod() {
    lock.lock();
    try {
        // critical section
    } finally {
        lock.unlock();
    }
}
```

## ExecutorService

```java
// Fixed thread pool
ExecutorService executor = Executors.newFixedThreadPool(4);

for (int i = 0; i < 10; i++) {
    executor.submit(() -> {
        System.out.println(Thread.currentThread().getName());
    });
}

executor.shutdown();
executor.awaitTermination(60, TimeUnit.SECONDS);
```

## Concurrent Collections

```java
// ConcurrentHashMap
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.put("key", 1);
map.computeIfAbsent("key", k -> 0);

// CopyOnWriteArrayList
CopyOnWriteArrayList<String> list = new CopyOnWriteArrayList<>();
list.add("item"); // Thread-safe
```

## CompletableFuture

```java
CompletableFuture.supplyAsync(() -> fetchData())
    .thenApply(data -> transform(data))
    .thenAccept(result -> System.out.println(result))
    .exceptionally(ex -> {
        System.out.println("Error: " + ex.getMessage());
        return null;
    });
```

## Atomic Variables

```java
AtomicInteger counter = new AtomicInteger(0);
counter.incrementAndGet(); // Thread-safe increment
counter.compareAndSet(5, 10); // CAS operation
```

## Common Pitfalls

1. **Race Conditions**: Multiple threads accessing shared mutable state
2. **Deadlocks**: Two threads waiting for each other's locks
3. **Starvation**: Thread never gets CPU time
4. **Livelock**: Threads keep changing state but make no progress
5. **Thread Safety**: Always use synchronization for shared mutable state
