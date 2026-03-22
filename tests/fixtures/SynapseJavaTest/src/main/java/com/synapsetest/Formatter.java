package com.synapsetest;

public final class Formatter {
    private Formatter() {}

    public static String format(String input) {
        return "[" + input + "]";
    }

    public static String formatAnimal(Animal animal) {
        return format(animal.getName() + ": " + animal.speak());
    }
}
