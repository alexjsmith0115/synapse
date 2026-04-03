package com.synappstest;

import org.springframework.beans.factory.annotation.Autowired;

public class OrderService {

    @Autowired
    private OrderRepository orderRepository;

    public Animal createAnimal(String name) {
        Animal animal = new Cat();
        return orderRepository.save(animal);
    }

    public long countAnimals() {
        return orderRepository.count();
    }
}
