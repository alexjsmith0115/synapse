import { Greeting } from '@/components/Greeting';
import { Dog } from './animals';

export function App() {
  const dog = new Dog("Rex");
  return <Greeting name={dog.getName()} />;
}
