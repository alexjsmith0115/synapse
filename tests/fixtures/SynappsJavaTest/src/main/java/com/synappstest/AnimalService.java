package com.synappstest;

import java.util.List;
import java.util.ArrayList;
import org.springframework.beans.factory.annotation.Autowired;
import javax.inject.Inject;

public class AnimalService {
    @Autowired
    private IAnimal animal;

    @Inject
    private Formatter formatter;

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

    public Runnable createTask() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(animal.speak());
            }
        };
    }

    @Deprecated
    public static synchronized void legacyMethod() {
        // Legacy code
    }
}
