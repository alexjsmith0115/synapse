package com.synapsetest;

import java.util.List;
import java.util.ArrayList;

public class AnimalService {
    private final IAnimal animal;

    public AnimalService(IAnimal animal) {
        this.animal = animal;
    }

    public String greet() {
        return "Hello, " + animal.speak();
    }

    public List<String> greetAll(List<IAnimal> animals) {
        List<String> greetings = new ArrayList<>();
        for (IAnimal a : animals) {
            greetings.add(Formatter.format(a.speak()));
        }
        return greetings;
    }

    @Deprecated
    public static synchronized void legacyMethod() {
        // Legacy code
    }
}
