# Java Exception Handling

## Exception Hierarchy

```
Throwable
├── Error (serious system errors)
│   ├── OutOfMemoryError
│   ├── StackOverflowError
│   └── VirtualMachineError
└── Exception
    ├── IOException
    ├── SQLException
    ├── RuntimeException (unchecked)
    │   ├── NullPointerException
    │   ├── ArrayIndexOutOfBoundsException
    │   ├── ArithmeticException
    │   ├── ClassCastException
    │   └── IllegalArgumentException
    └── Custom exceptions (checked)
```

## Try-Catch-Finally

```java
try {
    int result = 10 / 0;
} catch (ArithmeticException e) {
    System.out.println("Cannot divide by zero: " + e.getMessage());
} finally {
    System.out.println("This always executes");
}
```

## Multiple Catch Blocks

```java
try {
    // risky code
} catch (FileNotFoundException e) {
    System.out.println("File not found");
} catch (IOException e) {
    System.out.println("IO error");
} catch (Exception e) {
    System.out.println("General error");
}
```

## Try-With-Resources

```java
try (BufferedReader br = new BufferedReader(new FileReader("file.txt"))) {
    String line = br.readLine();
    System.out.println(line);
} catch (IOException e) {
    e.printStackTrace();
}
// Auto-close happens here
```

## Custom Exceptions

```java
public class InsufficientFundsException extends Exception {
    private double deficit;

    public InsufficientFundsException(double deficit) {
        super("Insufficient funds. Deficit: " + deficit);
        this.deficit = deficit;
    }

    public double getDeficit() {
        return deficit;
    }
}
```

## Checked vs Unchecked Exceptions

- **Checked**: Must be declared or caught (IOException, SQLException)
- **Unchecked**: RuntimeException and its subclasses (NullPointerException, etc.)
- **Error**: System-level errors (OutOfMemoryError)

## Best Practices

1. Use specific exception types, not generic Exception
2. Always clean up resources (try-with-resources)
3. Don't catch and ignore exceptions silently
4. Include meaningful messages in exceptions
5. Throw early, catch late
6. Use custom exceptions for business logic errors
