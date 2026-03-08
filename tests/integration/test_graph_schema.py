"""
Integration tests for the complete graph schema using a minimal synthetic C# project.

Covers every node label and edge type in the schema design. Uses a self-contained
project created in a temp directory so it does not depend on external repositories.

Requires FalkorDB running on localhost:6379 and .NET SDK installed.
Run with: pytest tests/integration/test_graph_schema.py -v -m integration
"""
import textwrap
from pathlib import Path

import pytest

from synapse.graph.connection import GraphConnection
from synapse.graph.schema import ensure_schema
from synapse.service import SynapseService


@pytest.fixture(scope="module")
def cs_project(tmp_path_factory) -> Path:
    """
    Minimal C# project exercising every node label and edge type:

    Node labels: Repository, Directory, File, Package, Class, Interface, Method, Property, Field
    Edge types:  CONTAINS (Dir→Dir, Dir→File, File→symbol, Package→symbol, Class→member),
                 IMPORTS, INHERITS (Class→Class, Interface→Interface),
                 IMPLEMENTS (Class→Interface), CALLS (Method→Method)
    """
    root = tmp_path_factory.mktemp("cs_schema_test")

    (root / "SchemaTest.csproj").write_text(textwrap.dedent("""\
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup>
            <TargetFramework>net9.0</TargetFramework>
          </PropertyGroup>
        </Project>
    """))

    models = root / "Models"
    models.mkdir()

    # IAnimal, IPet (interface INHERITS interface), Animal (abstract class IMPLEMENTS interface),
    # Dog (class INHERITS class, IMPLEMENTS interface), with Methods/Properties/Fields
    (models / "Animals.cs").write_text(textwrap.dedent("""\
        namespace SchemaTest.Models;

        public interface IAnimal
        {
            string Name { get; }
            void Speak();
        }

        public interface IPet : IAnimal
        {
            string Owner { get; }
        }

        public abstract class Animal : IAnimal
        {
            public string Name { get; set; } = "";
            protected int _age;

            public abstract void Speak();
        }

        public class Dog : Animal, IPet
        {
            public string Owner { get; set; } = "";

            public override void Speak()
            {
                MakeSound();
            }

            private void MakeSound()
            {
            }
        }
    """))

    services = root / "Services"
    services.mkdir()

    # AnimalService IMPORTS SchemaTest.Models via using directive
    (services / "AnimalService.cs").write_text(textwrap.dedent("""\
        using SchemaTest.Models;

        namespace SchemaTest.Services;

        public class AnimalService
        {
            public void Process(IAnimal animal)
            {
                animal.Speak();
            }
        }
    """))

    return root


@pytest.fixture(scope="module")
def service(cs_project) -> SynapseService:
    import subprocess
    subprocess.run(["dotnet", "restore"], cwd=cs_project, check=True, capture_output=True)
    conn = GraphConnection.create(graph_name="synapse_schema_test")
    ensure_schema(conn)
    conn.execute("MATCH (n) DETACH DELETE n")
    return SynapseService(conn)


def _count(service: SynapseService, query: str) -> int:
    rows = service.execute_query(query)
    return rows[0][0] if rows else 0


# ─── Indexing ────────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.timeout(120)
def test_index_cs_project(service, cs_project) -> None:
    service.index_project(str(cs_project), "csharp")
    assert _count(service, "MATCH (n:File) RETURN count(n)") >= 1


# ─── Node labels ─────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_file_nodes(service) -> None:
    # Animals.cs, AnimalService.cs
    assert _count(service, "MATCH (n:File) RETURN count(n)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_directory_nodes(service) -> None:
    # Models/, Services/ (plus root)
    assert _count(service, "MATCH (n:Directory) RETURN count(n)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_package_nodes(service) -> None:
    # SchemaTest.Models, SchemaTest.Services
    assert _count(service, "MATCH (n:Package) RETURN count(n)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_interface_nodes(service) -> None:
    # IAnimal, IPet
    assert _count(service, "MATCH (n:Interface) RETURN count(n)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_class_nodes(service) -> None:
    # Animal, Dog, AnimalService
    assert _count(service, "MATCH (n:Class) RETURN count(n)") >= 3


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_method_nodes(service) -> None:
    # Speak (×2: abstract + override), MakeSound, Process
    assert _count(service, "MATCH (n:Method) RETURN count(n)") >= 3


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_property_nodes(service) -> None:
    # Name, Owner
    assert _count(service, "MATCH (n:Property) RETURN count(n)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_field_nodes(service) -> None:
    # _age
    assert _count(service, "MATCH (n:Field) RETURN count(n)") >= 1


# ─── Edge types ──────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contains_dir_to_dir(service) -> None:
    # root → Models, root → Services
    assert _count(service, "MATCH (d1:Directory)-[:CONTAINS]->(d2:Directory) RETURN count(*)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contains_dir_to_file(service) -> None:
    # Models → Animals.cs, Services → AnimalService.cs
    assert _count(service, "MATCH (d:Directory)-[:CONTAINS]->(f:File) RETURN count(*)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contains_file_to_top_level_symbol(service) -> None:
    # File → Package (namespace is top-level in file)
    assert _count(service, "MATCH (f:File)-[:CONTAINS]->(n) RETURN count(*)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contains_package_to_class(service) -> None:
    # SchemaTest.Services → AnimalService
    assert _count(service, "MATCH (p:Package)-[:CONTAINS]->(c:Class) RETURN count(*)") >= 1


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contains_package_to_interface(service) -> None:
    # SchemaTest.Models → IAnimal, IPet
    assert _count(service, "MATCH (p:Package)-[:CONTAINS]->(i:Interface) RETURN count(*)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_contains_class_to_method(service) -> None:
    # Dog.Speak, Dog.MakeSound, AnimalService.Process, ...
    assert _count(service, "MATCH (c:Class)-[:CONTAINS]->(m:Method) RETURN count(*)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_inherits_class_to_class(service) -> None:
    # Dog → Animal
    assert _count(service, "MATCH (c:Class)-[:INHERITS]->(p:Class) RETURN count(*)") >= 1


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_inherits_interface_to_interface(service) -> None:
    # IPet → IAnimal
    assert _count(service, "MATCH (c:Interface)-[:INHERITS]->(p:Interface) RETURN count(*)") >= 1


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_implements_class_to_interface(service) -> None:
    # Animal → IAnimal, Dog → IPet
    assert _count(service, "MATCH (c:Class)-[:IMPLEMENTS]->(i:Interface) RETURN count(*)") >= 2


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_imports_file_to_package(service) -> None:
    # AnimalService.cs using SchemaTest.Models
    assert _count(service, "MATCH (f:File)-[:IMPORTS]->(p:Package) RETURN count(*)") >= 1


@pytest.mark.integration
@pytest.mark.timeout(10)
def test_calls_method_to_method(service) -> None:
    # Dog.Speak() → Dog.MakeSound()
    assert _count(service, "MATCH (m1:Method)-[:CALLS]->(m2:Method) RETURN count(*)") >= 1
