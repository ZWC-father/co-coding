# solution.py

def find(parent, x):
    """Find the root of x with path compression."""
    if parent[x] != x:
        parent[x] = find(parent, parent[x])  # Path compression
    return parent[x]

def union(parent, size, x, y):
    """Union two sets and return True if successful."""
    root_x = find(parent, x)
    root_y = find(parent, y)
    if root_x == root_y:
        return False  # Already connected
    # Union by size: smaller tree merges into larger tree
    if size[root_x] < size[root_y]:
        parent[root_x] = root_y
        size[root_y] += size[root_x]
    else:
        parent[root_y] = root_x
        size[root_x] += size[root_y]
    return True

def main():
    import sys
    input = sys.stdin.read().split()
    idx = 0
    n = int(input[idx])
    idx += 1
    m = int(input[idx])
    idx += 1

    edges = []
    # Process m edges
    for _ in range(m):
        u = int(input[idx])
        idx += 1
        v = int(input[idx])
        idx += 1
        w = int(input[idx])
        idx += 1
        if u != v:  # Discard self-loops
            edges.append((w, u, v))

    # Sort edges by weight (ascending)
    edges.sort()

    # Initialize Union-Find structures
    parent = dict()
    size = dict()
    def get_or_init(x):
        if x not in parent:
            parent[x] = x
            size[x] = 1
    # Initialize for all vertices in edges
    for w, u, v in edges:
        get_or_init(u)
        get_or_init(v)

    total_weight = 0
    edges_used = 0

    for w, u, v in edges:
        if find(parent, u) != find(parent, v):
            union(parent, size, u, v)
            total_weight += w
            edges_used += 1
            if edges_used == n - 1:
                break  # MST complete

    # Check if all vertices are connected
    # Get all unique vertices
    vertices = set()
    for w, u, v in edges:
        vertices.add(u)
        vertices.add(v)
    # If there are vertices not processed (no edges connected to them)
    if len(vertices) < n:
        # Incomplete graph
        print(-1)
        return

    # Check if all vertices are connected to the same root
    root_count = set(find(parent, v) for v in vertices if v in parent)
    if len(root_count) > 1:
        print(-1)
    else:
        print(total_weight)

if __name__ == "__main__":
    main()